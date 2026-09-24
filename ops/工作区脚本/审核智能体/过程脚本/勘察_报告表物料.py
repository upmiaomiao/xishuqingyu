#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：① 报告表的原辅材料在哪 ② 名录排序为何命中 66 而非 57。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.criteria import Criteria  # noqa: E402
from audit.extract import extract_materials, tables_with_header  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")


def main():
    rep = load_or_parse(os.path.join(ROOT, "1、环评报告.pdf"), cache_dir=CACHE)
    print("### 原辅材料相关正文命中")
    for h in rep.search(r"原辅材料|主要原辅料|原辅料|主要原料|原料及", max_hits=6, ctx=120):
        print(f"  P{h['page']} ({h.get('mark')}): {h['snippet'][:150]}")
    print("\n### 含『名称』+『单位』+『用量/数量』列的表")
    for t in tables_with_header(rep, need_name=True, need_qty=True, need_unit=True):
        print(f"  P{t['page']} 表头：{' | '.join(t['rows'][0])[:110]}")
        for r in t["rows"][1:5]:
            print("      | " + " | ".join(c[:20] for c in r))
    print("\n### 所有含『用量』或『消耗』的表")
    for t in rep.tables:
        if any(k in t["markdown"][:300] for k in ("用量", "消耗量", "年用量")):
            print(f"  P{t['page']} 表头：{' | '.join(t['rows'][0])[:110]}  ({len(t['rows'])}行)")
            for r in t["rows"][1:7]:
                print("      | " + " | ".join(c[:22] for c in r))
    print("\n### extract_materials 结果")
    ms = extract_materials(rep)
    print(f"  共 {len(ms)} 项：", [(m['名称'][:14], m['数量'], m['单位'], m['页码']) for m in ms[:8]])

    print("\n### 名录打分（项目名称作为查询）")
    C = Criteria()
    q = "江西省博信玻璃有限公司年产18 万吨建筑节能玻璃及太阳能光伏玻璃改扩建项目"
    C.find_items(q, top=5)
    for s, no, cat, w in C._last_scores:
        print(f"  score={s:4d} 序号{no:3d} {cat}  命中词={w}")


if __name__ == "__main__":
    main()