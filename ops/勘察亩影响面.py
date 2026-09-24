#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C10-① 的影响面勘察：名录里有多少条目的条件带"面积阈值"，以及语料里"亩"出现的规模。

只读。结论用于判断"改 criteria.py:71 那一行（亩=1.0 → 666.7）"的影响半径，
以及是否值得排期（影响面越小越容易安排回归）。
"""
from __future__ import annotations

import collections
import io
import json
import re
import sys
from pathlib import Path

CRIT = Path(sys.argv[1] if len(sys.argv) > 1 else r"判据库\分类管理名录2021.json")
CORPUS = Path(sys.argv[2] if len(sys.argv) > 2 else r"/data/fagui_rag/okf_bundles")


def main() -> int:
    d = json.load(io.open(CRIT, encoding="utf-8"))
    items = d if isinstance(d, list) else (d.get("条目") or d.get("items") or [])
    print("名录条目数：%d（来源 %s）" % (len(items), CRIT))
    c = collections.Counter()
    area_items = []
    for it in items:
        t = json.dumps(it, ensure_ascii=False)
        if "万平方米" in t:
            c["含「万平方米」"] += 1
        if "平方米" in t:
            c["含「平方米」（任意写法）"] += 1
            area_items.append((it, "平方米"))
        if re.search(r"亩", t):
            c["含「亩」"] += 1
            area_items.append((it, "亩"))
        if re.search(r"面积", t):
            c["含「面积」二字"] += 1
    for k, v in c.items():
        print("  %-22s %d 条" % (k, v))

    print("\n带面积阈值的条目（全部列出，看条件原文）：")
    seen = set()
    for it, kind in area_items:
        key = json.dumps(it, ensure_ascii=False)
        if key in seen:
            continue
        seen.add(key)
        name = it.get("项目类别") or it.get("名称") or it.get("类别") or "?"
        cond = it.get("条件") or it.get("定量条件") or it.get("判定条件") or ""
        if isinstance(cond, list):
            cond = "；".join(json.dumps(x, ensure_ascii=False) if isinstance(x, dict) else str(x)
                             for x in cond)
        print("  · [%s] %-30s %s" % (kind, str(name)[:30], str(cond)[:150]))
        if kind == "亩":
            for k2 in ("定量条件", "条件", "判定条件", "原文", "依据"):
                if it.get(k2):
                    print("       %s: %s" % (k2, str(it[k2])[:200]))

    # 语料侧：有多少份材料真的用到"亩"（决定这个 bug 会不会被触发）
    if CORPUS.is_dir():
        n_files = n_hit = 0
        samples = []
        for p in CORPUS.rglob("*.md"):
            n_files += 1
            try:
                t = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if re.search(r"\d+\s*亩", t):
                n_hit += 1
                if len(samples) < 6:
                    m = re.search(r".{0,40}\d+\s*亩.{0,40}", t)
                    samples.append("%s ｜ %s" % (p.name[:40], (m.group(0) if m else "").replace("\n", " ")))
        print("\n语料：%d 份 md，其中出现「数字+亩」的 %d 份" % (n_files, n_hit))
        for s in samples:
            print("  · %s" % s)
    else:
        print("\n（语料目录 %s 不在本机，跳过语料统计）" % CORPUS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
