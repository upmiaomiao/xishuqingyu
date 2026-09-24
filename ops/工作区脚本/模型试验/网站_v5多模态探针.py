#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：确认 .12:8000 的 xishu-qingyu-v5 能否直接吃图（多模态通路）。

用法：
  python 网站_v5多模态探针.py
"""
from __future__ import annotations

import base64
import io
import json
import os
import time

import httpx
from PIL import Image, ImageDraw, ImageFont

MODEL_URL = "http://10.201.31.12:8000/v1/chat/completions"
MODEL_NAME = "xishu-qingyu-v5"
SYSTEM = "你是生态环境法律与标准分析助手。请先在<think></think>标记中逐步推理分析，再给出最终结论。"


def make_test_image() -> str:
    img = Image.new("RGB", (760, 260), "white")
    d = ImageDraw.Draw(img)
    font = None
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 26)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    d.multiline_text((20, 30),
                     "自动监测数据异常核查任务\n"
                     "点位：1#焚烧炉 烟气排放口\n"
                     "颗粒物 日均值 12.5 mg/m³（限值 20）\n"
                     "核查状态：不属实   日期：2026-01-13",
                     fill="black", font=font, spacing=12)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--stream", action="store_true", help="走流式（生产实际用的通路）")
    ap.add_argument("--no-text", action="store_true", help="只发图、不打字")
    args = ap.parse_args()

    b64 = make_test_image()
    print(f"测试图 {len(b64)} b64 字符（≈{len(b64)*3//4//1024} KB）")

    parts = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
    if not args.no_text:
        parts.insert(0, {"type": "text", "text": "这张图片里写了什么？逐字转写，并说明这是什么材料。"})

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": parts},
        ],
        "temperature": 0,
        "max_tokens": 900,
        "stream": bool(args.stream),
    }

    if args.stream:
        t0 = time.time()
        n = 0
        buf = []
        with httpx.stream("POST", MODEL_URL, json=payload, timeout=300) as r:
            print(f"HTTP {r.status_code} (stream)")
            if r.status_code != 200:
                print(r.read()[:1500])
                return
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    break
                try:
                    d = json.loads(body)
                except Exception:
                    continue
                delta = d["choices"][0].get("delta", {})
                piece = delta.get("content") or ""
                if piece:
                    n += 1
                    buf.append(piece)
        print(f"首字到结束 {time.time()-t0:.1f}s，收到 {n} 个 chunk")
        text = "".join(buf)
        print(f"--- 全文前 600 字 ---\n{text[:600]}")
        print(f"--- 是否含 </think> ：{text.count('</think>')} 次 ---")
        return

    t0 = time.time()
    try:
        r = httpx.post(MODEL_URL, json=payload, timeout=300)
    except Exception as e:
        print(f"请求异常：{type(e).__name__}: {e}")
        return
    print(f"HTTP {r.status_code}  耗时 {time.time()-t0:.1f}s")
    if r.status_code != 200:
        print(r.text[:1500])
        return
    data = r.json()
    msg = data["choices"][0]["message"]
    print("--- content ---")
    print((msg.get("content") or "")[:1500])
    if msg.get("reasoning_content"):
        print("--- reasoning(前 400) ---")
        print(msg["reasoning_content"][:400])
    print("--- usage ---", json.dumps(data.get("usage", {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
