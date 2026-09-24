#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按"效果好的题型"从训练集里各抽若干条，写成候选清单（供人工挑选 20 条）。

效果证据（v5 焚烧测试 + 黄金样本判分）写进 EVIDENCE，随题一起落盘，便于汇报时对得上号。
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
OUT = WS / "_工作记录" / "垃圾焚烧好题型候选.jsonl"

TOPIC = ("垃圾焚烧", "生活垃圾焚烧", "垃圾发电", "焚烧炉", "焚烧厂", "炉排炉", "流化床",
         "渗滤液", "渗沥液", "飞灰", "炉渣", "烟气", "二噁英", "GB 18485", "GB18485",
         "HJ 1134", "余热锅炉", "热解气化", "垃圾热值", "燃烬", "SNCR", "SCR", "脱酸",
         "布袋除尘", "活性炭", "螯合", "固化", "填埋", "餐厨", "污泥")
DATATABLE = re.compile(r"炉膛上部温度\s*均值|百分位|料层厚度\s*均值|省煤器出口.*均值")

# 家族 → (效果证据, 抽几条)
PLAN = [
    ("patent_innovation_and_comparison", "v5 焚烧测试 heldout_03/04 均 4/5（边界 5、0 编造）；黄金样本同类判分 24.2/25", 5),
    ("trend_and_gap_analysis",           "v5 焚烧测试 heldout_09 满 5 分、heldout_10 4 分（全场最好的一类）", 5),
    ("standard_policy_interpretation",   "v5 焚烧测试 heldout_06 5 分（正确/覆盖/可操作全 5）；heldout_05 3 分（1 处编造）", 5),
    ("structured_drafting",              "v5 焚烧测试 heldout_07/08 均 3 分（中等，结构好、边界一般）", 5),
    ("paper_translation_and_digest",     "无直接测试分；同类「摘要/提炼」在黄金样本判 22.1/25", 4),
    ("case_to_deliverable",              "⚠️ 该类含运行数据表复盘（已知效果差：2-3 分、每题 5 处编造）——这里只取**非数据表**的", 4),
]


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def main():
    random.seed(20260919)
    src = WS / "原始训练数据" / "sft3_accepted_strict_merged.jsonl"
    buckets = {g: [] for g, _, _ in PLAN}
    for r in load(src):
        q = r.get("instruction", "")
        g = (r.get("metadata") or {}).get("group", "")
        if g not in buckets:
            continue
        if not any(k in q for k in TOPIC):
            continue
        if DATATABLE.search(q):
            continue
        if not (120 <= len(q) <= 900):
            continue
        buckets[g].append((q, r.get("metadata") or {}))

    out = []
    print("=" * 100)
    for g, ev, k in PLAN:
        pool = buckets[g]
        # 去重（同前缀只留一条）
        seen, uniq = set(), []
        for q, m in pool:
            key = q[:60]
            if key not in seen:
                seen.add(key)
                uniq.append((q, m))
        pick = random.sample(uniq, min(k, len(uniq)))
        print(f"\n■ {g}　候选 {len(uniq)} 条，抽 {len(pick)} 条")
        print(f"  效果证据：{ev}")
        for i, (q, m) in enumerate(pick, 1):
            out.append({"family": g, "evidence": ev, "question": q,
                        "source_file": "原始训练数据/sft3_accepted_strict_merged.jsonl",
                        "metadata": m})
            print(f"   [{len(out):>2}] {' '.join(q.split())[:150]}")
    OUT.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out),
                   encoding="utf-8")
    print(f"\n候选已写入 {OUT.relative_to(WS)}（{len(out)} 条，含完整题干与来源）")


if __name__ == "__main__":
    main()
