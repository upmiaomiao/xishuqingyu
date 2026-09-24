#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试：judge 接口到底回了什么（打印字段结构与原文前 600 字）。"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]


def dotenv(key: str) -> str | None:
    p = WS / ".env"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


key = os.environ.get("OPENAI_API_KEY") or dotenv("OPENAI_API_KEY")
base = (os.environ.get("OPENAI_BASE_URL") or dotenv("OPENAI_BASE_URL")).rstrip("/")
print("base =", base)
print("模型候选：", {k: dotenv(k) for k in ("GENERATE_MODEL", "FILTER_MODEL", "SEARCH_MODEL")})

for model in ("deepseek-v4-flash-guan", dotenv("FILTER_MODEL")):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": "只输出一个 JSON：{\"ok\": 1, \"msg\": \"hello\"}"}],
        "temperature": 0, "max_tokens": 300,
    }).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                headers={"Content-Type": "application/json",
                                         "Authorization": f"Bearer {key}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        msg = d["choices"][0]["message"]
        print(f"\n=== {model} ===  顶层键 {list(d.keys())}；message 键 {list(msg.keys())}")
        print("  finish_reason:", d["choices"][0].get("finish_reason"), " usage:", d.get("usage"))
        print("  content[:400]:", repr((msg.get("content") or "")[:400]))
        if msg.get("reasoning_content"):
            print("  reasoning_content[:300]:", repr(msg["reasoning_content"][:300]))
    except Exception as e:  # noqa: BLE001
        print(f"\n=== {model} === 失败：{type(e).__name__}: {str(e)[:200]}")
