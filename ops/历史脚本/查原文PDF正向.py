#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""/doc 正向用例：从索引里挑一个**确实有 PDF** 的 source，走 HTTP 验证能打开。

为什么要专门补：问答通道因检索服务挂掉，前端拿不到任何 source，
这条"点引用看原文"的路在网页上暂时走不到，只能直接按索引里的真实 source 打接口。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"
INDEX = "/data/fagui_rag/index/chunks.jsonl"
PDF_ROOT = "/data/fagui_pdf"

good, bad = None, None
with open(INDEX, encoding="utf-8") as f:
    for line in f:
        try:
            s = json.loads(line).get("source") or ""
        except Exception:                                      # noqa: BLE001
            continue
        if not s.lower().endswith(".md"):
            continue
        p = os.path.join(PDF_ROOT, s[:-3] + ".pdf")
        if os.path.isfile(p) and good is None:
            good = s
        if not os.path.isfile(p) and bad is None:
            bad = s
        if good and bad:
            break


def get(path, timeout=180):
    r = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, {}, str(e).encode()


def hget(h, n):
    for k, v in (h or {}).items():
        if k.lower() == n.lower():
            return v
    return ""


print("挑中的有 PDF 的 source : %s" % (good or "（没有）"))
print("挑中的缺 PDF 的 source : %s" % (bad or "（没有）"))
print()

if good:
    st, h, b = get("/doc?source=" + urllib.parse.quote(good))
    ok = st == 200 and b[:4] == b"%PDF"
    print("[正向] GET /doc?source=<有PDF的> → HTTP %s，%s，%d 字节" % (st, hget(h, "Content-Type"), len(b)))
    print("   %s 返回真的是 PDF" % ("√" if ok else "×"))
    print("   %s Content-Disposition 为 inline（浏览器内预览而非下载）"
          % ("√" if "inline" in hget(h, "Content-Disposition") else "× %s" % hget(h, "Content-Disposition")))
    print("   %s 文件名带 .pdf" % ("√" if ".pdf" in hget(h, "Content-Disposition") else "×"))

if bad:
    st, h, b = get("/doc?source=" + urllib.parse.quote(bad))
    print("\n[负向] GET /doc?source=<缺PDF的> → HTTP %s" % st)
    print("   %s 明确 404 并说明缺哪个文件" % ("√" if st == 404 else "×"))
    print("   detail: %s" % b.decode("utf-8", "replace")[:160])
