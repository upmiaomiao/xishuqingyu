#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顺带看一眼：这 20 条如果按「工艺域」摊开，分布在哪些方向（仅供对照，不是原分类轴）。"""
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in
        io.open(WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl", encoding="utf-8") if l.strip()]

# 工艺域关键词（题面里出现即算涉及）
DOMAINS = {
    "飞灰": r"飞灰",
    "炉渣/底渣": r"炉渣|底渣|集料",
    "烟气净化/脱硫脱硝": r"烟气|脱硫|脱硝|SCR|布袋|半干法",
    "二噁英": r"二噁英|PCDD|呋喃",
    "渗滤液/废水": r"渗滤液|废水|酸性废水",
    "炉型/燃烧": r"炉排|流化床|焚烧炉|燃烧|炉膛",
    "重金属": r"重金属|铅|镉|汞|Pb|Cd|Hg|锌|Zn",
    "监测/在线仪表": r"监测|在线|取样|测量|CEMS|遥感",
    "资源化利用": r"资源化|建材|沥青|水泥窑|协同处置",
}

hit = defaultdict(list)
for r in rows:
    q = r["题目"]
    for d, pat in DOMAINS.items():
        if re.search(pat, q, re.I):
            hit[d].append(r["序号"])

print("【按工艺域看这 20 条】（一条题可涉及多个域，仅作对照）")
for d, ids in sorted(hit.items(), key=lambda kv: -len(kv[1])):
    print(f"  {d:<18} {len(ids):>2} 条   序号 {ids}")

print("\n【原分类轴：题型】")
for k, v in Counter(r["题型"] for r in rows).most_common():
    print(f"  {k:<24} {v} 条   序号 {[r['序号'] for r in rows if r['题型'] == k]}")

print("\n【题面里完全没有出现焚烧工艺词的题】")
none = [r["序号"] for r in rows if not any(r["序号"] in v for v in hit.values())]
print("  ", none or "无")
