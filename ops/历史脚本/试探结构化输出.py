#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""试探：vLLM 的结构化输出能力能否强制模型吐 JSON。

如果 response_format / guided_json 有效，那照片研判的修法就明确且改动很小
（在 stream_model 调用处加一个参数），不需要改提示词或重训模型。
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

EP = "http://127.0.0.1:8020/v1/chat/completions"

SCHEMA = {
    "type": "object",
    "properties": {
        "image_type": {"type": "string"},
        "visible_facts": {"type": "array", "items": {"type": "string"}},
        "checklist": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "item": {"type": "string"},
                    "observed": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["满足", "不满足", "无法判断"]},
                    "basis": {"type": "string"},
                },
                "required": ["item", "observed", "verdict", "basis"],
            },
        },
        "waste_class": {"type": "string"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
        "uncertainty": {"type": "string"},
    },
    "required": ["image_type", "visible_facts", "checklist", "waste_class"],
}


def run(label, extra, msgs):
    body = {"model": "xishu-qingyu-v5", "messages": msgs, "max_tokens": 8192, "temperature": 0.0}
    body.update(extra)
    t0 = time.time()
    try:
        r = requests.post(EP, json=body, timeout=900)
    except Exception as e:                                        # noqa: BLE001
        print("  %-34s → 调用异常：%s" % (label, e))
        return
    dt = round(time.time() - t0, 1)
    if r.status_code != 200:
        print("  %-34s → HTTP %s：%s" % (label, r.status_code, r.text[:160]))
        return
    d = r.json()
    ch = d["choices"][0]
    txt = ch["message"].get("content") or ""
    obj = extract_json_object(txt)
    print("  %-34s → %s  finish=%s  %d 字  %.0fs"
          % (label, "✓ JSON 可解析" if obj else "× 仍非 JSON", ch.get("finish_reason"), len(txt), dt))
    if obj:
        print("        image_type=%r checklist=%d 项" % (str(obj.get("image_type"))[:20],
                                                        len(obj.get("checklist") or [])))
        vd = [c.get("verdict") for c in (obj.get("checklist") or []) if isinstance(c, dict)]
        print("        verdict 取值：%s" % vd)
    else:
        print("        原文开头：%s" % txt.split("</think>")[-1].strip()[:110].replace("\n", " "))


def main():
    raw = open("/home/test/_ab_photo.png", "rb").read()
    url = "data:image/png;base64," + base64.b64encode(raw).decode()
    msgs = photo_messages("未检索到可用资料。", url, "", "这张现场照片反映出哪些问题？")
    print("照片 %d 字节；同一提示词，只改请求参数\n" % len(raw))

    run("① 基线（现生产参数）", {}, msgs)
    run("② response_format=json_object", {"response_format": {"type": "json_object"}}, msgs)
    run("③ response_format=json_schema", {"response_format": {"type": "json_schema",
                                                             "json_schema": {"name": "photo", "schema": SCHEMA}}}, msgs)
    run("④ guided_json（vllm extra_body）", {"guided_json": SCHEMA}, msgs)
    run("⑤ structured_outputs.json", {"structured_outputs": {"json": SCHEMA}}, msgs)


if __name__ == "__main__":
    main()
