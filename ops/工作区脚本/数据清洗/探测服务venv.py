#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找出服务用的 python/venv，并测试能否装 PyMuPDF。"""
import os
import subprocess

LAUNCH = "/home/test/xishu_qingyu_serve/launch_xishu_qingyu_qa_8011.sh"
print("--- 启动脚本 ---")
if os.path.isfile(LAUNCH):
    print(open(LAUNCH, encoding="utf-8", errors="replace").read())
else:
    print("找不到", LAUNCH)

print("--- 候选 venv ---")
for d in ("/home/test/xishu_qingyu_serve", "/data/fagui_rag", "/home/test"):
    for name in (".venv", "venv", "env"):
        p = os.path.join(d, name, "bin", "python")
        if os.path.isfile(p):
            out = subprocess.run([p, "-c", "import numpy,fitz;print('numpy',numpy.__version__,'fitz ok')"],
                                 capture_output=True, text=True)
            print(f"  {p}: {(out.stdout or out.stderr).strip()[:120]}")

print("--- 正在跑的服务进程 ---")
out = subprocess.run("ps -eo pid,cmd | grep -e uvicorn -e xishu | grep -v grep",
                     shell=True, capture_output=True, text=True)
print(out.stdout.strip()[:800] or "(无)")

print("--- pip 源可达性 ---")
out = subprocess.run("timeout 25 pip3 download pymupdf -d /tmp/piptest --no-deps 2>&1 | tail -4",
                     shell=True, capture_output=True, text=True)
print(out.stdout.strip()[:600])
