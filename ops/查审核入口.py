#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：为 [021] 重跑摸清"入口怎么调、每份结果来自哪份报告"。不改任何东西。"""
from __future__ import annotations

import glob
import io
import json
import os
import re
import time

D = "/data/eia_audit/_审核结果"


def head(path: str, n: int = 40) -> None:
    print("\n" + "=" * 78)
    print("## " + path)
    if not os.path.exists(path):
        print("  （不存在）")
        return
    src = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
    for i, line in enumerate(src[:n], 1):
        print("%4d| %s" % (i, line[:130]))
    # 关键参数单独摘出来
    print("  ---- 参数/入口相关行 ----")
    for i, line in enumerate(src, 1):
        if re.search(r"add_argument|argparse|__main__|def main|sys\.argv|input_dir|--file|--report", line):
            print("%4d* %s" % (i, line.strip()[:130]))


for p in ("/data/eia_audit/run_audit.py", "/data/eia_audit/run_via_http.py"):
    head(p, 32)

print("\n" + "=" * 78)
print("## 现有结果（重跑对象）")
for f in sorted(glob.glob(os.path.join(D, "*.json")), key=os.path.getmtime):
    try:
        d = json.load(io.open(f, encoding="utf-8"))
    except Exception as exc:                                        # noqa: BLE001
        print("  %-52s 读不动：%s" % (os.path.basename(f)[:52], exc))
        continue
    src = str(d.get("file") or d.get("文件") or "")
    st = d.get("统计") or {}
    print("  %-50s" % os.path.basename(f)[:50])
    print("      来源：%s" % (src[:110] or "(未记录)"))
    print("      来源存在：%s ｜ 条数 %s ｜ 统计 %s"
          % (os.path.exists(src) if src else "?", len(d.get("items") or []), str(st)[:90]))
    print("      改时间：%s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f))))
