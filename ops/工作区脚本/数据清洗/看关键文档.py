#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看关键文档补了什么：对每份，打印"补后新增"的片段（骨架级定位），用于人工核对。

用法：看关键文档.py [stage目录]
"""
import difflib
import os
import re
import sys

sys.path.insert(0, "/tmp")
from importlib import import_module

m = import_module("语料正文回填")
BUNDLE = "/data/fagui_rag/okf_bundles"
STAGE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stage_probe"

CASES = [
    "国家危险废物名录",
    "储油库大气污染物排放标准（GB 20950—2020",
    "制糖工业水污染物排放标准（GB 21909-2008",
    "一般工业固体废物贮存和填埋污染控制标准 GB 18599",
]


def show(rel, n=3):
    old = open(os.path.join(BUNDLE, rel), encoding="utf-8", errors="replace").read()
    new = open(os.path.join(STAGE, rel), encoding="utf-8", errors="replace").read()
    print("=" * 78)
    print(f"{os.path.basename(rel)[:64]}")
    print(f"  {len(old):,} 字 → {len(new):,} 字  (+{len(new)-len(old):,})")
    sm = difflib.SequenceMatcher(None, old, new, autojunk=True)
    shown = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in ("insert", "replace"):
            continue
        ins = new[j1:j2]
        if len(ins.strip()) < 15:
            continue
        shown += 1
        print(f"  --- 新增块 {shown}（{len(ins)} 字） 上文: "
              f"{' '.join(old[max(0,i1-50):i1].split())[-45:]!r}")
        print(f"      {' '.join(ins.split())[:400]}")
        if shown >= n:
            break
    # 候选数值形态探测
    for pat, label in [(r"\d{3}-\d{3}-\d{2}", "危废代码 900-001-01 形态"),
                       (r"\bHW\d{2}\b", "HW 类别码"),
                       (r"6\s*[~～-]\s*9", "pH 6~9"),
                       (r"1\.0\s*[×xX✕]\s*10", "渗透系数 1.0×10-5")]:
        hits = re.findall(pat, new)
        if hits:
            print(f"  · {label}: {len(hits)} 处，例如 {hits[:4]}")


for kw in CASES:
    found = []
    for dp, _dn, fn in os.walk(STAGE):
        for f in fn:
            if f.endswith(".md") and kw in f:
                found.append(os.path.relpath(os.path.join(dp, f), STAGE))
    for rel in found:
        show(rel)
