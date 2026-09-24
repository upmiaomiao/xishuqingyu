#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端验证修法：加 response_format 后，站点自己的 render_photo_report 能否渲染成功。

这条链是：photo_messages → 模型 → extract_json_object → render_photo_report
本脚本只把「模型调用」换成带 response_format 的版本，其余全用站点原函数，
从而证明「只加一个请求参数」就能让结构化研判真正渲染出来。
"""
from __future__ import annotations

import base64
import sys
import time

sys.path.insert(0, "/home/test/xishu_qingyu_serve")

import requests                                                       # noqa: E402
from xishu_pipeline.compose import photo_messages                      # noqa: E402
from xishu_pipeline.postprocess import (extract_json_object,           # noqa: E402
                                        photo_render_note, render_photo_report)

EP = "http://127.0.0.1:8020/v1/chat/completions"


def main():
    raw = open("/home/test/_ab_photo.png", "rb").read()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()

    # 用一段真实法规上下文，贴近生产
    ctx = (
        "[1] 《一般工业固体废物贮存和填埋污染控制标准》\n"
        "贮存场应设置防扬散、防流失、防渗漏措施，不相容的一般工业固体废物应分区贮存，"
        "并设置环境保护图形标志。\n\n"
        "[2] 《危险废物贮存污染控制标准》\n"
        "危险废物贮存设施应设置防雨、防晒、防渗漏设施，并设置危险废物识别标志。"
    )
    msgs = photo_messages(ctx, url, "", "这张现场照片反映出哪些问题？")

    for label, extra in [("现状（无 response_format）", {}),
                         ("修法（response_format=json_object）", {"response_format": {"type": "json_object"}})]:
        body = {"model": "xishu-qingyu-v5", "messages": msgs, "max_tokens": 8192,
                "temperature": 0.0, "chat_template_kwargs": {"enable_thinking": True}}
        body.update(extra)
        t0 = time.time()
        r = requests.post(EP, json=body, timeout=900)
        txt = r.json()["choices"][0]["message"].get("content") or ""
        obj = extract_json_object(txt)
        print("=" * 78)
        print("【%s】  %.0fs  %d 字" % (label, time.time() - t0, len(txt)))
        if obj is None:
            print("  → 走到生产的回退分支：")
            print("     ⚠️ 本次未能解析出结构化研判结果（已自动纠错重试一次）…")
            print("     用户看到的是模型原文，不是核验清单。")
            continue
        report, stats = render_photo_report(obj)
        report += photo_render_note(stats, False)
        print("  → 渲染成功，用户看到的是：")
        print("-" * 78)
        print(report)
        print("-" * 78)
        print("  渲染统计：%s" % stats)


if __name__ == "__main__":
    main()
