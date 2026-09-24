#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 _中间产物 顶层散落的实验产物收进归档 —— 但只动"没有任何文档/脚本引用"的。

判断依据：该文件名在 项目须知.md、_工作记录/**/*.md、_脚本代码/** 里出现过几次。
出现过的一律不动（怕把别人的路径弄断），只移动 0 次引用的。
"""
from __future__ import annotations

import shutil
from pathlib import Path

WS = Path(__file__).resolve().parents[2]      # 本文件在 _脚本代码/服务器运维/ 下
MID = WS / "_中间产物"
ARCH = MID / "_散落实验产物_0911至0913"

# 收集"引用底本"
docs: list[Path] = [WS / "项目须知.md"]
for root in (WS / "_工作记录", WS / "_脚本代码"):
    docs += [p for p in root.rglob("*") if p.is_file() and p.suffix in (".md", ".py", ".sh")
             and "__pycache__" not in p.parts]
text_blob = ""
for p in docs:
    try:
        text_blob += p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        pass
print(f"引用底本 {len(docs)} 个文件，共 {len(text_blob):,} 字符")

ARCH.mkdir(parents=True, exist_ok=True)
moved, kept = [], []
for p in sorted(MID.iterdir()):
    if p.is_dir() or p.name.startswith("."):
        continue
    n = text_blob.count(p.name)
    if n == 0:
        shutil.move(str(p), str(ARCH / p.name))
        moved.append(p.name)
    else:
        kept.append(f"{p.name}（被引用 {n} 次）")

if not moved:
    ARCH.rmdir()                # 一个都没动就别留空目录
    print("\n没有任何文件满足归档条件（全部都被引用）")
else:
    print(f"\n归档 {len(moved)} 个无人引用的散落文件 → {ARCH.relative_to(WS)}")
    for m in moved:
        print(f"  · {m}")
print(f"\n保留 {len(kept)} 个（有引用，动不得）：")
for k in kept:
    print(f"  · {k}")
