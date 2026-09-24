#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从训练集里抽候选题：按家族分组，只保留**题干真的在讲垃圾焚烧**的。

"讲垃圾焚烧"判据：题干（不含 system 身份声明）里出现行业词，
且不属于"运行数据表复盘"那种程序化生成的工况题（那类已知效果差：数值臆补）。
"""
from __future__ import annotations

import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

WS = Path(__file__).resolve().parents[2]

# 题干里出现这些词 = 行业主题是垃圾焚烧/垃圾发电
TOPIC = ("垃圾焚烧", "生活垃圾焚烧", "垃圾发电", "焚烧炉", "焚烧厂", "炉排炉", "流化床",
         "渗滤液", "渗沥液", "飞灰", "炉渣", "烟气", "二噁英", "GB 18485", "GB18485",
         "HJ 1134", "余热锅炉", "热解气化", "垃圾热值", "燃烬", "SNCR", "SCR", "脱酸",
         "布袋除尘", "活性炭", "螯合", "固化", "填埋", "餐厨", "污泥")
# 已知效果差的家族特征：程序化生成的运行数据复盘题（答案带题干未给的百分位）
DATATABLE = re.compile(r"炉膛上部温度\s*均值|百分位|料层厚度\s*均值|省煤器出口.*均值")


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ask_of(rec: dict) -> str:
    if "instruction" in rec:
        return rec["instruction"]
    msgs = rec.get("messages", [])
    for m in msgs:
        if m.get("role") == "user":
            return m.get("content", "")
    return ""


def main():
    random.seed(20260919)
    src = WS / "原始训练数据" / "sft3_accepted_strict_merged.jsonl"
    fam = defaultdict(list)
    n_total = n_topic = 0
    for r in load(src):
        n_total += 1
        q = ask_of(r)
        if not any(k in q for k in TOPIC):
            continue
        n_topic += 1
        g = (r.get("metadata") or {}).get("group", "?")
        fam[g].append((q, bool(DATATABLE.search(q))))
    print(f"sft3_accepted_strict_merged：共 {n_total} 条，题干含垃圾焚烧主题词 {n_topic} 条 "
          f"（{n_topic/n_total*100:.1f}%）\n")
    print(f"{'家族':<38}{'主题题数':>8}{'其中数据表题':>12}")
    for g, v in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        dt = sum(1 for _, d in v if d)
        print(f"{g:<38}{len(v):>8}{dt:>12}")

    print("\n" + "=" * 100)
    print("每个家族抽 2 条看长相（跳过数据表题）")
    for g, v in sorted(fam.items(), key=lambda kv: -len(kv[1])):
        cands = [q for q, d in v if not d and 80 <= len(q) <= 700]
        if not cands:
            continue
        print(f"\n── {g}（候选 {len(cands)} 条）")
        for q in random.sample(cands, min(2, len(cands))):
            print(f"   · {q[:230]}")


if __name__ == "__main__":
    main()
