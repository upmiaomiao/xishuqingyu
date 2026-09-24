#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看几个可疑推导的原文上下文（调规则前先看事实，不猜）。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")

CASES = [
    ("1、环评报告.pdf", r"新增[^。\n]{0,10}(河道|地表水)[^。\n]{0,6}取水|取水口[^。\n]{0,20}(河道|河|地表水)", "玻璃-取水"),
    ("1、环评报告.pdf", r"500\s*m\s*(?:范围)?内", "玻璃-500m"),
    ("1邵武市生活垃圾焚烧发电项目（公示稿).pdf", r"(废水|污水)[^。\n]{0,20}(直排|直接排入)", "邵武-直排"),
    ("1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.pdf",
     r"(废水|污水)[^。\n]{0,30}(排入|纳入|接入|接管)[^。\n]{0,20}(污水处理厂|污水厂|管网)", "临沂-废水去向"),
]


def main():
    for fn, pat, label in CASES:
        rep = load_or_parse(os.path.join(ROOT, fn), cache_dir=CACHE)
        print(f"\n### {label}  /{pat}/")
        for h in rep.search(pat, max_hits=4, ctx=110):
            print(f"  P{h['page']} ({h.get('mark')}): {h['snippet']}")


if __name__ == "__main__":
    main()