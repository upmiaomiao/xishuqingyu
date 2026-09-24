#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""视觉模型探针：确认 dmxapi 上可用于「网站上传照片」的视觉模型是否可用。

用法：
  python 网站_视觉模型探针.py                  # 用多模态视觉模型
  python 网站_视觉模型探针.py --model <name>

不打印任何密钥。
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import re
import sys
import time

import httpx
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))          # _脚本代码/模型试验
ROOT = os.path.dirname(os.path.dirname(HERE))              # 工作区根
ENV = os.path.join(ROOT, ".env")
SITE = os.path.join(ROOT, "服务器会话", "服务端", "xishu_qingyu_qa_线上版.py")

DEFAULT_MODEL = "deepseek-v4-flash-vision-exp-guan"


def api_key() -> str:
    """优先 .env，其次线上站点文件里的 INTENT_API_KEY。"""
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            m = re.match(r"\s*OPENAI_API_KEY\s*=\s*(\S+)", line)
            if m:
                return m.group(1)
    txt = open(SITE, encoding="utf-8").read()
    m = re.search(r'INTENT_API_KEY\s*=\s*"([^"]+)"', txt)
    if not m:
        sys.exit("找不到 API key")
    return m.group(1)


def make_test_image(text: str = "颗粒物 超标 12.5 mg/m³\n2026-01-13 生活垃圾焚烧厂") -> str:
    """生成一张带中文与数值的测试图（模拟用户上传的截图/照片）。"""
    img = Image.new("RGB", (720, 240), "white")
    d = ImageDraw.Draw(img)
    font = None
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"):
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, 28)
                break
            except Exception:
                pass
    if font is None:
        font = ImageFont.load_default()
    d.multiline_text((24, 40), text, fill="black", font=font, spacing=16)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    print(f"测试图：720x240 PNG，{len(buf.getvalue())} bytes")
    return base64.b64encode(buf.getvalue()).decode()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--base-url", default="https://www.dmxapi.cn/v1")
    args = ap.parse_args()

    key = api_key()
    print(f"key: {key[:6]}…{key[-4:]}（长度 {len(key)}）")
    print(f"model: {args.model}")

    b64 = make_test_image()
    payload = {
        "model": args.model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图片里写了什么？请逐字转写，并说明它看起来是什么类型的材料。"},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ],
        }],
        "max_tokens": 800,
        "temperature": 0,
    }

    t0 = time.time()
    try:
        r = httpx.post(
            f"{args.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json=payload,
            timeout=120,
        )
    except Exception as e:
        print(f"请求异常：{type(e).__name__}: {e}")
        return

    print(f"HTTP {r.status_code}  耗时 {time.time()-t0:.1f}s")
    if r.status_code != 200:
        print(r.text[:800])
        return
    data = r.json()
    msg = data["choices"][0]["message"]
    print("--- content ---")
    print((msg.get("content") or "")[:1200])
    if msg.get("reasoning_content"):
        print("--- reasoning(前 300 字) ---")
        print(msg["reasoning_content"][:300])
    print("--- usage ---")
    print(json.dumps(data.get("usage", {}), ensure_ascii=False))


if __name__ == "__main__":
    main()
