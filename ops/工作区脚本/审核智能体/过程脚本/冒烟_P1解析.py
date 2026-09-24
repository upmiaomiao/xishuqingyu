#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 冒烟测试：解析层对 8 份报告产出的结构化包是否可信。

检查项（都是机械可判的）：
  1. 每份 PDF 有文本层（字/页 > 120），页数、表格数、锚点命中数
  2. 页眉页脚是否被剔除（running 行清单）
  3. 章节树是否来自内置目录
  4. **锚点页码抽查**：拿锚点片段回原文核对（页码 → 该页文本确实包含锚点词）
  5. 页号映射：物理页 ↔ 印刷页 的偏移是否稳定（抽查若干页）
  6. 表格可读性：抽 3 张表打印前几行
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")


def main():
    names = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".pdf"))
    print(f"待解析 {len(names)} 份\n")
    for name in names:
        p = os.path.join(ROOT, name)
        try:
            rep = load_or_parse(p, cache_dir=CACHE, with_tables=True, verbose=True)
        except Exception as e:
            print(f"!! {name} 解析失败：{e.__class__.__name__}: {e}")
            continue
        chars = sum(len(t) for t in rep.page_text)
        print(f"=== {name[:56]}")
        print(f"    {rep.pages} 页  {chars:,} 字  {chars / max(rep.pages,1):.0f} 字/页  "
              f"表格 {len(rep.tables)} 张  章节 {len(rep.toc)} 条 "
              f"({'内置目录' if rep.toc and rep.toc[0].get('from_toc') else '正则重建'})")
        print(f"    运行页眉/页脚剔除 {len(rep.running_lines)} 行，示例 "
              f"{[r[:28] for r in rep.running_lines[:3]]}")
        print(f"    页号映射 {len(rep.page_labels)} 页有标签；"
              f"示例 {list(rep.page_labels.items())[:5]}")
        hits = {k: (v[0]['page'], v[0]['printed_page']) for k, v in rep.anchors.items() if v}
        print(f"    锚点命中 {len(hits)}/{len(rep.anchors)}：{hits}")

        # 锚点页码抽查（机械核对：命中的原文必须真的在该页文本里）
        bad = checked = 0
        for k, v in rep.anchors.items():
            for h in v[:3]:
                checked += 1
                pg, txt = h["page"], h["match"]
                if txt not in rep.page_text[pg - 1]:
                    bad += 1
                    print(f"      !! 锚点 {k} 声称 P{pg} 含 {txt!r}，但该页文本里找不到")
        print(f"    锚点页码核对：抽查 {checked} 条，{'全部一致 ✅' if not bad else f'不一致 {bad} 条 ❌'}")

        for t in rep.tables[:2]:
            print(f"    表 p{t['page']}（印刷页 {t['printed_page']}）"
                  f"{len(t['rows'])}行×{max(len(r) for r in t['rows'])}列")
            for r in t["rows"][:3]:
                print("      | " + " | ".join(c[:18] for c in r))
        print()


if __name__ == "__main__":
    sys.exit(main())