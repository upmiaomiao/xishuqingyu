#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用**真实**现场照片跑 report=photo，检查它在检索服务挂掉时的行为。

设计前提（pipeline.py 第 78 行注释原文）：
  「现场照片专业研判：独立通路，不走意图路由（判定要有依据，必须检索）」
但第 92-97 行是：
  try: found = retriever.retrieve(...)
  except Exception: sources = []
也就是**检索失败被静默吞掉**，然后拿"未检索到可用资料。"去让模型下判定。
本脚本就是来验这件事：这种情况下用户到底看到了什么。
"""
from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMG = os.path.join(ROOT, "image", "固废垃圾.png")


def post(payload, timeout=600):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + "/hybrid_search", data=body,
                               headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode()


if not os.path.isfile(IMG):
    sys.exit("找不到测试图片：%s" % IMG)
raw = open(IMG, "rb").read()
url = "data:image/png;base64," + base64.b64encode(raw).decode()
print("测试照片：%s（%d 字节，data URL %d 字符）\n" % (os.path.basename(IMG), len(raw), len(url)))

st, b = post({"query": "这张现场照片反映出哪些问题？", "image": url, "report": "photo"})
try:
    d = json.loads(b.decode("utf-8"))
except Exception:                                              # noqa: BLE001
    d = {}
print("HTTP %s" % st)
print("route        : %r" % d.get("route"))
print("sources 条数 : %d  ← 设计上这里必须有依据，为 0 即等于「无依据下判定」"
      % len(d.get("sources") or []))
print("image_note   : %s" % (d.get("image_note") or "")[:120].replace("\n", " "))
ans = d.get("answer") or ""
print("answer 长度  : %d" % len(ans))
print("-" * 74)
print(ans[:1400])
print("-" * 74)
if st != 200:
    print("detail: %s" % str(d.get("detail"))[:200])
