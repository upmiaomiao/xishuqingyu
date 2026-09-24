#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断模型抽取的拦截原因：看候选页、模型原始输出、定位短语、依据片段。"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.extract_llm import QUESTIONS, candidate_pages  # noqa: E402
from audit.llm import ask_pages  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "1、环评报告.pdf"
    rep = load_or_parse(os.path.join(ROOT, name), cache_dir=CACHE)
    print(f"=== {name[:50]}  {rep.pages} 页")
    for spec in QUESTIONS:
        pages = candidate_pages(rep, spec, 6)
        r = ask_pages(rep, spec["q"], pages, require_keywords=spec["kw"])
        print(f"\n--- {spec['key']}   候选页={pages}")
        print(f"    raw={repr((r.get('_raw') or '')[:220])}")
        print(f"    value={r.get('value')} page={r.get('page')} anchor={str(r.get('anchor'))[:90]}")
        print(f"    quote={str(r.get('quote'))[:150]}")
        print(f"    _verified={r.get('_verified')}  "
              + (f"_reject={r.get('_reject')}" if r.get("_reject") else ""))


if __name__ == "__main__":
    main()