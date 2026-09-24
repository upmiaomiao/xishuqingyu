#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""客观核验实跑结果：数字可追溯性 + 检索质量（不依赖 LLM 裁判）。

核验项：
  ① 答案里的具体数值，有多少能在【题干 + 本轮引用正文】里找到（找不到 = 无出处数字）
     口径沿用 v5 焚烧测试报告：只统计 ≥2 位的数字（避开"一、二、3T"这类序号）
  ② 检索质量：rerank 分、doc_type 构成、同一文档被重复引用
  ③ 引用的标准是否现行（status 字段）
  ④ 题目点名的标准号有没有被引到
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
IN = WS / "_工作记录" / "实跑20条_输出v2.jsonl"
OUT = WS / "_工作记录" / "实跑20条_客观核验.md"

NUM = re.compile(r"\d+(?:\.\d+)?")
rows = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]


def nums(text: str) -> Counter:
    """抽出长度≥2 或带小数的数字（去掉纯个位序号干扰）。"""
    c: Counter = Counter()
    for m in NUM.finditer(text or ""):
        t = m.group(0)
        if len(t.replace(".", "")) >= 2:
            c[t.rstrip("0").rstrip(".") if "." in t else t] += 1
    return c


L = ["# 20 条实跑：客观核验（数字可出处 + 检索质量）", "",
     "口径：答案里的数值若在【题干】或【本轮 8 条引用正文】里找不到，记为「无出处数字」"
     "（沿用 v5 焚烧测试报告的口径；只统计 ≥2 位有效数字，排除个位序号）。", "",
     "| # | 题型 | 答案数字 | 其中有出处 | 无出处 | 无出处占比 | rerank最高 | 引用构成 | 重复引用 |",
     "|---|---|---|---|---|---|---|---|---|"]

tot_n = tot_miss = 0
miss_detail = []
for r in rows:
    q_text = r["题目"]
    src_text = " ".join((s.get("text") or "") for s in (r.get("引用") or []))
    ans = r.get("答案") or ""
    ans_nums = nums(ans)
    have = nums(q_text + " " + src_text)
    miss = {k: v for k, v in ans_nums.items() if k not in have}
    n_all = sum(ans_nums.values())
    n_miss = sum(miss.values())
    tot_n += n_all
    tot_miss += n_miss
    dts = r.get("doc_type分布") or {}
    comp = " ".join(f"{k}:{v}" for k, v in sorted(dts.items(), key=lambda kv: -kv[1]))
    L.append(f"| {r['序号']} | {r['题型']} | {n_all} | {n_all - n_miss} | {n_miss} | "
             f"{n_miss/max(1,n_all)*100:.0f}% | {r.get('rerank_top1'):.3f} | {comp} | "
             f"{r.get('标题重复数')} |")
    if miss:
        miss_detail.append((r["序号"], r["题型"], sorted(miss.items(), key=lambda kv: -kv[1])[:8],
                            n_miss / max(1, n_all)))

L += ["", f"**合计**：答案数字 {tot_n} 个，其中**无出处 {tot_miss} 个（{tot_miss/max(1,tot_n)*100:.1f}%）**", "",
      "## 无出处数字最多的几条", ""]
for no, t, items, pct in sorted(miss_detail, key=lambda x: -x[3])[:8]:
    L.append(f"- **[{no}] {t}**（无出处 {pct*100:.0f}%）：" +
             "、".join(f"{k}×{v}" for k, v in items))

# 检索质量汇总
rr = [r["rerank_top1"] for r in rows if isinstance(r.get("rerank_top1"), (int, float))]
dts_all = Counter()
for r in rows:
    dts_all.update(r.get("doc_type分布") or {})
L += ["", "## 检索质量汇总", "",
      f"- rerank 最高分：平均 {sum(rr)/len(rr):.3f}，最低三条 "
      + "、".join(f"#{r['序号']}={r['rerank_top1']:.3f}" for r in sorted(rows, key=lambda x: x.get("rerank_top1") or 0)[:3]),
      f"- 引用文档类型构成：{dict(dts_all)}（`?` = 知识图谱节点，没有 doc_type）",
      f"- 同一文档被重复引用：合计 {sum(r['标题重复数'] for r in rows)} 处", "",
      "| # | 引用标题 |", "|---|---|"]
for r in rows:
    if r["标题重复数"]:
        ts = Counter(s.get("title") or "" for s in r["引用"])
        dup = "；".join(f"{t}×{c}" for t, c in ts.items() if c > 1)
        L.append(f"| {r['序号']} | {dup} |")

# 标准现行性
L += ["", "## 引用的标准/法规是否现行", ""]
st = Counter()
bad = []
for r in rows:
    for s in r["引用"]:
        st[s.get("status") or "（空）"] += 1
        if (s.get("status") or "") not in ("现行", "已公开", ""):
            bad.append((r["序号"], s.get("title"), s.get("status")))
L.append(f"- status 构成：{dict(st)}")
for no, t, s in bad:
    L.append(f"- ⚠️ [{no}] {t} → {s}")

# 题目点名标准号的命中
L += ["", "## 题目点名的标准号 vs 引用命中", "", "| # | 题目点名 | 引用正文命中 |", "|---|---|---|"]
for r in rows:
    L.append(f"| {r['序号']} | {', '.join(r['题目中的标准号']) or '—'} | "
             f"{', '.join(r['引用正文命中的标准号']) or '—'} |")

OUT.write_text("\n".join(L), encoding="utf-8")
print("\n".join(L[:34]))
print(f"\n→ {OUT.relative_to(WS)}")
