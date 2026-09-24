#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用真实端点验证照片研判修法：POST /hybrid_search/stream 带 report=photo。

判定标准（不看模型自述，只看结构化标记）：
  通过 = 正文含「【一、图片类型】」且含「【三、核验清单】」的表格，
         且**不含**回退告警「本次未能解析出结构化研判结果」。
  失败 = 出现回退告警。
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011"
PHOTO = sys.argv[1] if len(sys.argv) > 1 else "/home/test/_photo_verify.png"

raw = open(PHOTO, "rb").read()
url = "data:image/png;base64," + base64.b64encode(raw).decode()
print("图片：%s  %d 字节" % (PHOTO, len(raw)))

body = json.dumps({
    "query": "这张现场照片反映出哪些问题？",
    "history": [],
    "image": url,
    "report": "photo",
}, ensure_ascii=False).encode("utf-8")

req = urllib.request.Request(BASE + "/hybrid_search/stream", data=body,
                            headers={"Content-Type": "application/json"}, method="POST")
t0 = time.time()
ev = None
data_buf: list[str] = []
text = ""
route = None
sources = 0

with urllib.request.urlopen(req, timeout=900) as resp:
    dec = iter(resp)
    buf = b""
    for chunk in resp:
        buf += chunk
        while b"\n" in buf:
            line, buf = buf.split(b"\n", 1)
            line = line.decode("utf-8", "replace").strip()
            if not line:
                continue
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                payload = line[5:].strip()
                if ev == "chunk":
                    text += json.loads(payload)
                elif ev in ("meta", "done"):
                    d = json.loads(payload)
                    route = d.get("route") or route
                    sources = len(d.get("sources") or []) or sources
                elif ev == "status":
                    print("  [status] %s" % json.loads(payload).get("message"))
                elif ev == "error":
                    print("  [error] %s" % payload)

el = round(time.time() - t0, 1)
print("\nroute=%s  来源 %d 条  用时 %.1fs  正文 %d 字" % (route, sources, el, len(text)))

print("\n" + "=" * 72)
FALLBACK = "本次未能解析出结构化研判结果"
has_type = "【一、图片类型】" in text
has_list = "【三、核验清单】" in text
has_table = "| 检查项 |" in text or "| --- |" in text
has_fb = FALLBACK in text

print("含「【一、图片类型】」      : %s" % has_type)
print("含「【三、核验清单】」      : %s" % has_list)
print("含核验清单表格              : %s" % has_table)
print("含回退告警（应为 False）    : %s" % has_fb)
print()
if has_type and has_list and not has_fb:
    print("★★★ 通过：结构化研判已渲染 ★★★")
else:
    print("✗ 未通过")

print("=" * 72)
print("正文前 1200 字：")
print(text[:1200])
