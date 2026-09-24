#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找报告自述的行业类别 / 国民经济行业分类代码（名录匹配的第一依据）。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")
FILES = ["1、环评报告.pdf", "生物质环评.pdf",
         "1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.pdf"]
PAT = (r"行业类别|行业分类|国民经济行业|C\s?3\d{3}|C\s?4\d{3}|D\s?4\d{3}|"
       r"N\s?7\d{3}|属于.{0,10}行业")


def main():
    for fn in FILES:
        rep = load_or_parse(os.path.join(ROOT, fn), cache_dir=CACHE)
        print(f"\n##### {fn[:44]} ({rep.pages}页)")
        seen = set()
        for h in rep.search(PAT, max_hits=8, ctx=100):
            if h["page"] in seen:
                continue
            seen.add(h["page"])
            print(f"  P{h['page']} ({h.get('mark')}): {h['snippet'][:190]}")
        # 表里含"行业类别"单元
        for t in rep.tables:
            for r in t["rows"]:
                joined = " | ".join(r)
                if "行业类别" in joined or "行业分类" in joined:
                    print(f"  [表] P{t['page']}: {joined[:200]}")


if __name__ == "__main__":
    main()