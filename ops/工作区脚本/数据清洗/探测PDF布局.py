#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""确认 /data/fagui_pdf 的目录布局，看能否由 bundle md 的 source_path 直接定位 PDF。"""
import os

PDF_ROOT = "/data/fagui_pdf"
BUNDLE = "/data/fagui_rag/okf_bundles"

print("--- /data/fagui_pdf 顶层 ---")
for x in sorted(os.listdir(PDF_ROOT))[:12]:
    p = os.path.join(PDF_ROOT, x)
    print(f"  {'DIR ' if os.path.isdir(p) else 'FILE'} {x}")

# 抽 3 份 bundle md，读出 source_path，验证 PDF 是否存在
import json
import re

n = 0
for dp, _dn, fn in os.walk(BUNDLE):
    for f in fn:
        if not f.endswith(".md"):
            continue
        p = os.path.join(dp, f)
        t = open(p, encoding="utf-8", errors="replace").read()
        m = re.search(r"^source_path:\s*(.+)$", t, re.M)
        if not m:
            continue
        src = m.group(1).strip()
        cand = os.path.join(PDF_ROOT, os.path.splitext(src)[0] + ".pdf")
        has_imgref = "![](images/" in t
        print(f"\n  md  : {os.path.relpath(p, BUNDLE)[:80]}")
        print(f"  src : {src[:90]}")
        print(f"  PDF : {'存在' if os.path.isfile(cand) else '缺失'}  {os.path.getsize(cand) if os.path.isfile(cand) else ''}")
        print(f"  含图片引用: {has_imgref}   正文字数: {len(t)}")
        n += 1
        if n >= 4:
            break
    if n >= 4:
        break
