#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""定位「带图走 general 通道时答案为空」：看 reasoning / answer 的分布与原始增量。

用法：python 网站_空答案探针.py [base]
"""
import base64
import io
import json
import sys

import httpx
from PIL import Image, ImageDraw

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8012"


def img(text="collected data table", size=(300, 120)) -> str:
    im = Image.new("RGB", size, "white")
    ImageDraw.Draw(im).text((10, 50), text, fill="black")
    b = io.BytesIO()
    im.save(b, format="PNG")
    return "data:image/png;base64," + base64.b64encode(b.getvalue()).decode()


for label, payload in [
    ("图片+文字（小图/英文）", {"query": "这张图说明了什么？", "history": [], "image": img()}),
    ("只发图（小图/英文）", {"query": "", "history": [], "image": img()}),
]:
    ev = {"reasoning": "", "answer": "", "route": "", "raw": [], "status": []}
    with httpx.stream("POST", f"{BASE}/hybrid_search/stream", json=payload, timeout=300) as r:
        e = d = None
        for line in r.iter_lines():
            s = line.strip()
            if s.startswith("event:"):
                e = s[6:].strip()
            elif s.startswith("data:"):
                d = s[5:].strip()
            elif s == "":
                if not e:
                    continue
                try:
                    p = json.loads(d) if d else None
                except Exception:
                    p = None
                if e == "reasoning":
                    ev["reasoning"] += p if isinstance(p, str) else ""
                elif e == "chunk":
                    ev["answer"] += p if isinstance(p, str) else ""
                elif e in ("meta", "done"):
                    ev["route"] = (p or {}).get("route", ev["route"])
                elif e == "status":
                    ev["status"].append((p or {}).get("message"))
                elif e == "vision":
                    ev["raw"].append("VISION:" + str(p)[:80])
                elif e == "error":
                    ev["raw"].append("ERROR:" + str(p)[:200])
                e = d = None
    print(f"\n=== {label} ===")
    print(f"route={ev['route']} reasoning={len(ev['reasoning'])}字 answer={len(ev['answer'])}字")
    print(f"status: {ev['status']}")
    if ev["raw"]:
        print(f"其他事件: {ev['raw'][:3]}")
    print(f"reasoning 尾部 200 字: ...{ev['reasoning'][-200:]!r}")
    print(f"answer: {ev['answer'][:200]!r}")
