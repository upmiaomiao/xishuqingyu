#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环境探测：服务器上做语料回填所需的条件是否具备。"""
import os
import shutil
import subprocess
import sys

print("python", sys.version.split()[0])

for mod in ("fitz", "pdfplumber", "numpy"):
    try:
        m = __import__(mod)
        print(f"  {mod}: OK  {getattr(m, '__version__', getattr(m, '__doc__', ''))!s:.60}")
    except Exception as e:
        print(f"  {mod}: 缺失 ({e.__class__.__name__})")

for d in ("/data/fagui_rag", "/data/fagui_rag/okf_bundles", "/data/fagui_rag/index", "/data/fagui_pdf"):
    if os.path.isdir(d):
        n = sum(len(f) for _, _, f in os.walk(d))
        sz = subprocess.run(["du", "-sh", d], capture_output=True, text=True).stdout.split()[0]
        print(f"  {d}: {n} 个文件  {sz}")
    else:
        print(f"  {d}: 不存在")

print("pip:", shutil.which("pip3") or shutil.which("pip") or "无")
print("磁盘:", subprocess.run(["df", "-h", "/data"], capture_output=True, text=True).stdout.strip().splitlines()[-1])

p = ("/data/fagui_rag/okf_bundles/生态环境标准规范/水环境保护/水环境保护_附件123/"
     "水污染物排放标准_附件72/制糖工业水污染物排放标准 GB 21909-2008/"
     "制糖工业水污染物排放标准 GB 21909-2008.md")
if os.path.isfile(p):
    print("--- bundle md 头部 ---")
    print(open(p, encoding="utf-8").read()[:700])
