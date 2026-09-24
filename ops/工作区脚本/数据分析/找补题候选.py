#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从三个题库里找「补工艺域」的候选题。

筛选逻辑：
  1) 只留垃圾焚烧相关（题面出现焚烧/垃圾/飞灰/炉渣/二噁英/渗滤液…）；
  2) 按工艺域打标，统计哪些域在现有 20 条里偏少（炉渣、渗滤液、二噁英、监测、资源化）；
  3) 训练集只取效果好的 family；黄金样本/专业案例带上已有判分。
输出：_中间产物/补题候选.json（含候选清单，供人工/后续挑选）
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WS = Path(__file__).resolve().parents[2]

DOMAINS = {
    "飞灰": r"飞灰",
    "炉渣/底渣": r"炉渣|底渣|渣料|集料|熔渣",
    "烟气净化": r"脱硫|脱硝|SCR|SNCR|布袋|半干法|烟气净化|活性炭",
    "二噁英": r"二噁英|PCDD|PCDF|呋喃",
    "渗滤液/废水": r"渗滤液|废水|渗沥液|酸性废水|污水处理",
    "炉型/燃烧": r"炉排|流化床|焚烧炉|炉膛|燃烧|配风|一次风|二次风",
    "重金属": r"重金属|铅|镉|汞|Pb|Cd|Hg|锌|Zn|铬|砷",
    "监测/仪表": r"在线监测|CEMS|取样|测量|仪表|传感器|软测量|DCS|遥感",
    "资源化利用": r"资源化|建材|沥青|水泥窑|协同处置|制砖|陶粒",
}
WTE = r"焚烧|垃圾|飞灰|炉渣|二噁英|渗滤液|烟气|炉排|流化床"
GOOD_FAMILIES = {"patent_innovation_and_comparison", "trend_and_gap_analysis",
                 "standard_policy_interpretation", "structured_drafting",
                 "paper_translation_and_digest"}


def domains_of(text: str) -> list[str]:
    return [d for d, pat in DOMAINS.items() if re.search(pat, text, re.I)]


def load(path: Path):
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def main() -> int:
    # ---- 现有 20 条的域覆盖（作为"缺什么"的基准）----
    have = [json.loads(l) for l in
            io.open(WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl", encoding="utf-8") if l.strip()]
    base = Counter()
    for r in have:
        for d in domains_of(r["题目"]):
            base[d] += 1
    print("现有 20 条的工艺域覆盖：")
    for d in DOMAINS:
        print(f"  {d:<12} {base.get(d, 0):>2} 条")

    cands = []
    # ---- 训练集 ----
    fam = Counter()
    for i, o in enumerate(load(WS / "原始训练数据" / "sft3_accepted_strict_merged.jsonl")):
        q = o.get("instruction") or ""
        if not re.search(WTE, q):
            continue
        md = o.get("metadata") or {}
        f = md.get("family") or md.get("group") or ""
        fam[f] += 1
        if f not in GOOD_FAMILIES:
            continue
        ds = domains_of(q)
        if not ds:
            continue
        cands.append({"库": "训练集", "序号": f"train#{i}", "family": f, "工艺域": ds,
                      "题面": q, "判分": None})
    print(f"\n训练集 family 分布（焚烧相关）：{dict(fam.most_common(10))}")

    # ---- 黄金样本 ----
    for i, o in enumerate(load(WS / "黄金样本" / "golden_judged.jsonl")):
        q = o.get("question") or ""
        if not re.search(WTE, q):
            continue
        j = o.get("judge") or {}
        ds = domains_of(q)
        r = o.get("total")
        cands.append({"库": "黄金样本", "序号": f"gold#{i}", "family": o.get("type"),
                      "工艺域": ds, "题面": q,
                      "判分": {"总分": r, "五维": j}})

    # ---- 专业案例 ----
    for i, o in enumerate(load(WS / "专业案例" / "专业难题展示案例.jsonl")):
        q = o.get("question") or ""
        if not re.search(WTE, q):
            continue
        cands.append({"库": "专业案例", "序号": f"case#{i}", "family": o.get("family"),
                      "工艺域": domains_of(q), "题面": q,
                      "判分": {"score": o.get("score"), "难度": o.get("diff"),
                               "引用": o.get("sources"), "judge": o.get("judge")}})

    # ---- 按"补缺"打分：优先覆盖现有条数少的域 ----
    def gap_score(ds: list[str]) -> float:
        return sum(max(0, 4 - base.get(d, 0)) for d in ds)

    cands.sort(key=lambda c: -gap_score(c["工艺域"]))
    out = WS / "_中间产物" / "补题候选.json"
    out.write_text(json.dumps(cands, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n候选共 {len(cands)} 条 → {out.relative_to(WS)}")
    print("\n按补缺分排前 26 条：")
    for c in cands[:26]:
        j = c["判分"]
        tag = ""
        if j:
            tag = f" 判分={j.get('总分') or j.get('score')}"
        print(f"  {c['库']:<5} {c['序号']:<11} {str(c['family'])[:30]:<32}"
              f" {','.join(c['工艺域'])[:26]:<28}{tag}")
        print(f"        {c['题面'][:78]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
