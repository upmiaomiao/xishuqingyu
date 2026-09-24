#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""照片研判 JSON 契约遵从性 A/B。

目的：判定「未能解析出结构化研判结果」是
  (a) 本次迁移引入的，还是
  (b) 模型本身的契约遵从问题（迁移前后一样）。

做法：用站点自己的 compose.photo_messages 构造提示词（与生产逐字相同），
分别打 .10:8020 与 .12:8000，再各自用站点自己的 extract_json_object 解析。
同时对照「有参考资料 / 无参考资料」两种上下文，验证
compose.py 注释里那条「看到参考资料就写散文」的判断是否成立。
"""
from __future__ import annotations

import base64
import json
import sys
import time

sys.path.insert(0, "/home/test/xishu_qingyu_serve")

import requests                                                   # noqa: E402
from xishu_pipeline.compose import photo_messages                  # noqa: E402
from xishu_pipeline.postprocess import extract_json_object         # noqa: E402

IMG = "/home/test/_ab_photo.png"
ENDPOINTS = [
    (".10:8020（现生产）", "http://127.0.0.1:8020/v1/chat/completions"),
    (".12:8000（迁移前）", "http://10.201.31.12:8000/v1/chat/completions"),
]


def build_context() -> str:
    """用站点自己的检索链取真实参考资料，复刻生产上下文。"""
    try:
        sys.path.insert(0, "/data/fagui_rag")
        import retriever as R                                    # noqa: E402
        from xishu_pipeline.prompts import PHOTO_QUERY_SUFFIX    # noqa: E402
        rt = R.Retriever()
        found = rt.retrieve(f"这张现场照片反映出哪些问题？ {PHOTO_QUERY_SUFFIX}", 20, 5)
        srcs = [{"index": i + 1, "title": (c[2].get("title") or c[2].get("source") or "?"),
                 "text": c[2].get("text", "")} for i, c in enumerate(found)]
        return "\n\n".join("[%d] 《%s》\n%s" % (s["index"], s["title"], s["text"]) for s in srcs), len(srcs)
    except Exception as e:                                        # noqa: BLE001
        print("  ! 检索失败（改用空上下文）：%s" % e)
        return "未检索到可用资料。", 0


def call(ep: str, msgs: list, temp: float, maxtok: int = 8192) -> dict:
    body = {"model": "xishu-qingyu-v5", "messages": msgs,
            "max_tokens": maxtok, "temperature": temp}
    t0 = time.time()
    try:
        r = requests.post(ep, json=body, timeout=900)
    except Exception as e:                                        # noqa: BLE001
        return {"err": str(e)}
    dt = round(time.time() - t0, 1)
    if r.status_code != 200:
        return {"err": "HTTP %s %s" % (r.status_code, r.text[:200]), "dt": dt}
    d = r.json()
    ch = d["choices"][0]
    txt = ch["message"].get("content") or ""
    obj = extract_json_object(txt)
    return {"dt": dt, "finish": ch.get("finish_reason"), "usage": d.get("usage"),
            "len": len(txt), "json_ok": obj is not None, "obj": obj, "txt": txt}


def main():
    raw = open(IMG, "rb").read()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    print("测试照片：%d 字节\n" % len(raw))

    ctx, n = build_context()
    print("真实参考资料：%d 条，%d 字符\n" % (n, len(ctx)))

    cases = [("有参考资料（生产实况）", ctx), ("无参考资料（对照）", "未检索到可用资料。")]

    for cname, c in cases:
        print("=" * 78)
        print("【上下文】%s" % cname)
        for ename, ep in ENDPOINTS:
            for temp in (0.0, 0.3):
                msgs = photo_messages(c, url, "", "这张现场照片反映出哪些问题？")
                r = call(ep, msgs, temp)
                if "err" in r:
                    print("  %-18s temp=%.1f  → 调用失败：%s" % (ename, temp, r["err"][:90]))
                    continue
                print("  %-18s temp=%.1f  → %s  finish=%s  %d 字  %.0fs"
                      % (ename, temp, "✓ JSON 可解析" if r["json_ok"] else "× 解析失败",
                         r["finish"], r["len"], r["dt"]))
                if r["json_ok"]:
                    o = r["obj"]
                    print("        image_type=%r  facts=%d  checklist=%d  keys=%s"
                          % (str(o.get("image_type"))[:24], len(o.get("visible_facts") or []),
                             len(o.get("checklist") or []), sorted(o.keys())[:8]))
                else:
                    head = r["txt"].split("</think>")[-1].strip()[:150].replace("\n", " ")
                    print("        原文开头：%s" % head)
                    print("        含 'verdict' 字样：%s；含 '{' ：%s"
                          % ("verdict" in r["txt"], "{" in r["txt"]))
        print()


if __name__ == "__main__":
    main()
