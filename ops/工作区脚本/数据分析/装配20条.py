#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""装配「垃圾焚烧好题型 20 条」：题干逐字取自数据，不改写；每条带题型与效果证据。

来源：
  A. 原始训练数据/sft3_accepted_strict_merged.jsonl —— 严格过滤后**已被接受**进入训练集的样本
  B. 黄金样本/golden_judged.jsonl —— 有五维判分
  C. 专业案例/专业难题展示案例.jsonl —— 有总分（满分 25）

输出：
  _工作记录/垃圾焚烧好题型20条.jsonl   机器可读（含完整题干）
  _工作记录/垃圾焚烧好题型20条.md      人读（分类 + 证据 + 题干）
"""
from __future__ import annotations

import json
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
CAND = WS / "_工作记录" / "垃圾焚烧好题型候选.jsonl"
OUT_J = WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl"
OUT_M = WS / "_工作记录" / "垃圾焚烧好题型20条.md"

FAM_EV = {
    "patent_innovation_and_comparison":
        "v5 焚烧测试 heldout_03/04 双题 4/5（边界 5、0 处编造）；专业案例同类题 20/25",
    "trend_and_gap_analysis":
        "v5 焚烧测试 heldout_09 **满分 5/5**、heldout_10 4/5 —— 全场最好的一类",
    "standard_policy_interpretation":
        "v5 焚烧测试 heldout_06 **5/5**（正确/覆盖/可操作全 5）；黄金样本同类 5/5/5/5/5",
    "structured_drafting":
        "v5 焚烧测试 heldout_07/08 均 3/5（结构好、边界一般）；专业案例同类 18/25",
    "paper_translation_and_digest":
        "无同题测试分；同类「摘要/提炼」在黄金样本判 22.1/25",
}
FAM_CN = {
    "patent_innovation_and_comparison": "专利创新与对比",
    "trend_and_gap_analysis": "趋势与差距分析",
    "standard_policy_interpretation": "标准/政策解读",
    "structured_drafting": "结构化撰写（方案/培训/框架）",
    "paper_translation_and_digest": "技术摘要与提炼",
}


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


cand = list(load(CAND))
by_fam: dict[str, list[dict]] = {}
for c in cand:
    by_fam.setdefault(c["family"], []).append(c)


def take(fam: str, i: int) -> dict:
    return by_fam[fam][i]


items: list[dict] = []


def add(no, typ, q, src, ev, lang="中文"):
    items.append({"序号": no, "题型": typ, "题目": " ".join(q.split()),
                  "来源": src, "效果证据": ev, "语言": lang})


# ── A. 训练集（family 级证据）
for i in range(4):
    c = take("patent_innovation_and_comparison", i)
    add(len(items) + 1, FAM_CN[c["family"]], c["question"],
        "训练集 sft3_accepted（accepted）· family=patent_innovation_and_comparison",
        FAM_EV[c["family"]])
for i in range(4):
    c = take("trend_and_gap_analysis", i)
    add(len(items) + 1, FAM_CN[c["family"]], c["question"],
        "训练集 sft3_accepted（accepted）· family=trend_and_gap_analysis",
        FAM_EV[c["family"]])
for i in range(3):
    c = take("standard_policy_interpretation", i)
    add(len(items) + 1, FAM_CN[c["family"]], c["question"],
        "训练集 sft3_accepted（accepted）· family=standard_policy_interpretation",
        FAM_EV[c["family"]])
for i in (1, 2, 3):                      # 跳过第 0 条（二噁英排放统计偏数据型）
    c = take("structured_drafting", i)
    add(len(items) + 1, FAM_CN[c["family"]], c["question"],
        "训练集 sft3_accepted（accepted）· family=structured_drafting",
        FAM_EV[c["family"]])
for i in (0,):                           # 只取 1 条，凑满 20
    c = take("paper_translation_and_digest", i)
    add(len(items) + 1, FAM_CN[c["family"]], c["question"],
        "训练集 sft3_accepted（accepted）· family=paper_translation_and_digest",
        FAM_EV[c["family"]])

# ── B. 带直接判分的中文焚烧题（黄金样本 五维满分）
gold = list(load(WS / "黄金样本" / "golden_judged.jsonl"))
want_key = ("乾县", "浸出毒性")   # 两条 5/5/5/5/5
picked = []
for r in gold:
    q = r["question"]
    if r.get("type") != "wte_zh":
        continue
    if any(k in q for k in want_key) and q not in [p[0] for p in picked]:
        d = r.get("judge") or {}
        picked.append((q, d, r.get("total")))
for q, d, tot in picked[:2]:
    five = "/".join(str(d.get(k, "?")) for k in
                    ("correctness", "comprehensiveness", "structure", "actionability", "grounding"))
    add(len(items) + 1, "合规审查（法规依据直答）", q,
        "黄金样本 golden_judged.jsonl · type=wte_zh",
        f"judge 五维 {five}（满分 5/5/5/5/5），综合 {tot}")

# ── C. 专业案例（有总分）
pro = [r for r in load(WS / "专业案例" / "专业难题展示案例.jsonl") if "HJ 179" in r["question"]]
for r in pro[:1]:
    d = r.get("judge") or {}
    add(len(items) + 1, "标准适用性判断", r["question"],
        "专业案例/专业难题展示案例.jsonl（RAG 路线，8 条引用）",
        f"总分 {r.get('score')}/25，难度 {d.get('difficulty')}，judge="
        f"{ {k: v for k, v in d.items() if k != 'brief'} }")

# ── D. 现场故障诊断（英文，判分最高的一类）
en = [r for r in gold if r.get("type") == "wte_en/field"]
for r in en[:2]:
    d = r.get("judge") or {}
    five = "/".join(str(d.get(k, "?")) for k in
                    ("correctness", "comprehensiveness", "structure", "actionability", "grounding"))
    add(len(items) + 1, "现场运行与故障诊断", r["question"],
        "黄金样本 golden_judged.jsonl · type=wte_en/field",
        f"judge 五维 {five}；该类型 8 条均分 23.5/25（全部落在 5/5 结构分）", lang="英文")

OUT_J.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in items), encoding="utf-8")

# ── markdown
lines = ["# 垃圾焚烧「效果好」题型 20 条（2026-09-19 从项目数据里挑的）", "",
         "判据（都是项目里已有的实测，不是感觉）：", "",
         "| 证据来源 | 说明 |", "|---|---|",
         "| **v5 焚烧测试**（18 题） | 题型级效果：趋势差距 5/5、专利创新 4/5、标准政策解读 5/5、"
         "结构化撰写 3/5；**运行数据复盘 2–3/5（每题 5 处数值臆补，不推荐）** |",
         "| **黄金样本判分**（63 条） | `wte_zh` 22.9/25、`cot_law/ANALYSIS` 24.2/25 |",
         "| **专业案例判分**（11 条） | 焚烧类 18–20/25（RAG 路线、6–8 条引用） |", "",
         "来源构成：**第 1–15 条来自训练集**（`sft3_accepted_strict_merged.jsonl`，严格过滤后已被接受的样本）；"
         "**第 16–18 条来自带判分的展示集**（黄金样本 2 条五维满分 + 专业案例 1 条 19/25）；"
         "**第 19–20 条是英文现场诊断类**（`wte_en/field`，8 条均分 23.5/25，是判分最高的一类）。", "",
         "---", ""]
cur = None
for it in items:
    if it["题型"] != cur:
        cur = it["题型"]
        lines += [f"## {cur}", ""]
    q = it["题目"]
    show = q if len(q) <= 420 else q[:420] + "……（全文见同名 JSONL）"
    lines += [f"**{it['序号']}.** {show}", "",
              f"- 来源：`{it['来源']}`",
              f"- 效果证据：{it['效果证据']}", ""]
OUT_M.write_text("\n".join(lines), encoding="utf-8")

print(f"共 {len(items)} 条 → {OUT_J.relative_to(WS)} / {OUT_M.relative_to(WS)}\n")
for it in items:
    print(f"{it['序号']:>2} [{it['题型']}] {it['题目'][:78]}")
