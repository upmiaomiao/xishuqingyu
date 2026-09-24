#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看回填效果：对某份文档，打印"新文有、原文没有"的插入块及上下文。

用法：看回填效果.py <relpath> [块数]
需先设置 BUNDLE / STAGE 环境变量（默认 /data/fagui_rag/okf_bundles 与 /tmp/stage_probe）。
"""
import difflib
import os
import re
import sys

BUNDLE = os.environ.get("BUNDLE", "/data/fagui_rag/okf_bundles")
STAGE = os.environ.get("STAGE", "/tmp/stage_probe")
IMG_RE = re.compile(r"!\[\]\(images/[0-9A-Za-z._-]+\.(?:jpg|jpeg|png)\)")


def main():
    rel = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 3
    old = open(os.path.join(BUNDLE, rel), encoding="utf-8", errors="replace").read()
    new = open(os.path.join(STAGE, rel), encoding="utf-8", errors="replace").read()
    print(f"原文 {len(old):,} 字 → 新文 {len(new):,} 字  (+{len(new)-len(old):,})")
    print(f"残留死链：原 {len(IMG_RE.findall(old))} 处 → 新 {len(IMG_RE.findall(new))} 处")

    sm = difflib.SequenceMatcher(None, old, new, autojunk=False)
    shown = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag not in ("insert", "replace"):
            continue
        ins = new[j1:j2]
        if len(ins.strip()) < 20:
            continue
        shown += 1
        ctx_before = " ".join(old[max(0, i1 - 70):i1].split())[-60:]
        ctx_after = " ".join(new[j2:j2 + 70].split())[:60]
        print(f"\n{'='*76}\n[插入 {shown}] {len(ins)} 字")
        print(f"  上文: …{ctx_before}")
        print(f"  插入: {' '.join(ins.split())[:600]}")
        print(f"  下文: {ctx_after}…")
        if shown >= n:
            break
    print(f"\n共 {sum(1 for t,_,_,_,_ in sm.get_opcodes() if t in ('insert','replace'))} 个变更块，显示 {shown} 个")


if __name__ == "__main__":
    main()
