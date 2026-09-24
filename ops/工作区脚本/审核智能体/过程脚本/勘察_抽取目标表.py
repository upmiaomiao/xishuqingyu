#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""勘察：报告里抽取层要用到的几张表长什么样（决定表驱动抽取的匹配规则）。

看四类目标：
  1. 原辅材料表（名称/年用量/单位/形态/是否溶剂型）
  2. 专项评价设置情况（报告自述"设置/不设置"）
  3. 危险物质/风险物质（名称/CAS/最大存在量）
  4. 环评文件类型与项目基本信息（报告书 or 报告表）
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

KEYS = {
    "原辅材料": r"原辅材料|主要原辅料|原辅料一览|主要原料",
    "专项评价": r"专项评价",
    "风险物质": r"危险物质|风险物质|最大存在量|临界量",
    "基本情况": r"建设项目基本情况|项目名称.*行业类别",
}


def show(rep, tag, pattern, max_tables=3, max_pages=2):
    print(f"\n########## {tag}  正则={pattern}")
    hits = rep.search(pattern, max_hits=max_pages)
    for h in hits:
        pg = h["page"]
        print(f"  -- P{pg} (mark {h['mark']}) … {h['snippet'][:90]}")
    tabs = [t for t in rep.tables if re.search(pattern, " ".join(
        " ".join(r) for r in t["rows"][:2]) + " " + t["markdown"][:400])]
    print(f"  表头命中该关键词的表：{len(tabs)} 张")
    for t in tabs[:max_tables]:
        print(f"   表 P{t['page']} {len(t['rows'])}行×{max(len(r) for r in t['rows'])}列")
        for r in t["rows"][:6]:
            print("      | " + " | ".join(c[:22] for c in r))


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.pdf"
    rep = load_or_parse(os.path.join(ROOT, name), cache_dir=CACHE, with_tables=True)
    print(f"=== {name[:60]}  {rep.pages} 页  表 {len(rep.tables)} 张")
    for tag, pat in KEYS.items():
        show(rep, tag, pat)

    # 各锚点附近页内的表格
    print("\n########## 原辅材料锚点附近的表")
    for h in rep.anchors.get("原辅材料", [])[:2]:
        pg = h["page"]
        for t in rep.tables:
            if abs(t["page"] - pg) <= 2:
                print(f"   表 P{t['page']}  {len(t['rows'])}行")
                for r in t["rows"][:8]:
                    print("      | " + " | ".join(c[:20] for c in r))


if __name__ == "__main__":
    sys.exit(main())