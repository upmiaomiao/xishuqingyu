#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型抽取冒烟：3 个已知答案的问题 + 1 个陷阱题（考它会不会编）。

已知答案（已人工从原文确认）：
  1. 玻璃报告表 废水是否直排 → 否（纳管进桑海污水处理厂）
  2. 玻璃报告表 是否新增河道取水 → 需看原文（P98 那条是规划环评里别的取水口，不该算）
  3. 邵武报告书 废水是否直排 → 待查（P324 那条是"未直接排入"）
陷阱题：问一个报告里根本没有的事实，模型必须 found=false（敢说"不知道"才算合格）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.llm import ask_pages, call_model  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")

Q_WASTE = ("本项目的运营期废水最终去向是什么？请判断是否属于『直接排入环境水体（直排）』。"
           "若废水经厂内处理后纳入市政管网或进入污水处理厂，或全部回用不外排，则属于不直排。"
           "（关键词：废水、污水、排放、回用）")
Q_INTAKE = ("本项目生产用水的水源是什么？是否属于『新增河道（地表水）取水』？"
            "若水源为市政自来水或自来水管网，则不属于新增河道取水。"
            "（关键词：取水、水源、用水、供水）")
Q_TRAP = "本项目是否配套建设了海水淡化装置？日处理能力是多少？（关键词：海水淡化）"

KEYWORDS = {"废水去向/是否直排": ["废水", "污水", "排放", "回用", "水"],
            "取水水源/是否新增河道取水": ["取水", "水源", "用水", "供水"],
            "陷阱题（应 found=false）": ["海水淡化"]}


def main():
    name = "1、环评报告.pdf"
    rep = load_or_parse(os.path.join(ROOT, name), cache_dir=CACHE)
    print(f"=== {name[:40]}  {rep.pages} 页")

    # 候选页：机械缩小范围（水平衡/给排水/废水去向相关的锚点页）
    pages = []
    for anc in ("水平衡", "地表水", "产污环节"):
        for h in rep.anchors.get(anc, [])[:1]:
            pages += list(range(h["page"], min(rep.pages, h["page"] + 3) + 1))
    pages = sorted(set(p for p in pages if 1 <= p <= rep.pages))[:10]
    print(f"  候选页（机械缩小）：{pages}")

    for q, label in ((Q_WASTE, "废水去向/是否直排"), (Q_INTAKE, "取水水源/是否新增河道取水"),
                     (Q_TRAP, "陷阱题（应 found=false）")):
        r = ask_pages(rep, q, pages, require_keywords=KEYWORDS[label])
        print(f"\n  --- {label}  用时 {r.get('_secs')}s  解析方式={r.get('parsed_by')}")
        print(f"      value={r.get('value')} page={r.get('page')} verified={r.get('_verified')}")
        print(f"      定位短语={str(r.get('anchor'))[:80]}")
        print(f"      依据片段={str(r.get('quote'))[:150]}")
        if r.get("_reject"):
            print(f"      !! {r['_reject']}")


if __name__ == "__main__":
    main()