#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把补 12 条的实跑+判分写成报告。

输入：_工作记录/实跑补12条_输出.jsonl、实跑补12条_评分.jsonl
输出：_工作记录/2026-09-21-补12条工艺域题型实跑.md
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
D = WS / "_工作记录"
OUT = D / "2026-09-21-补12条工艺域题型实跑.md"
DIMS = (("correctness", "正确"), ("coverage", "覆盖"), ("actionability", "可操作"),
        ("grounding", "有据"), ("boundary", "边界"))
RE_NUM = re.compile(r"\d+(?:\.\d+)?")


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def main() -> int:
    runs = {r["序号"]: r for r in load(D / "实跑补12条_输出.jsonl")}
    sc = {r["序号"]: r for r in load(D / "实跑补12条_评分.jsonl")}
    items = {r["序号"]: r for r in load(D / "垃圾焚烧好题型_补12条.jsonl")}
    old = {r["序号"]: r for r in load(D / "实跑20条_输出v2.jsonl")}
    oldsc = {}
    p = D / "实跑20条_评分v2.jsonl"
    if p.is_file():
        oldsc = {r["序号"]: r for r in load(p)}

    rows = [r for r in runs.values()]
    scored = [s for s in sc.values() if isinstance(s.get("均分"), (int, float))]

    def avg(dim: str, src=None):
        v = [s[dim] for s in (src or scored) if isinstance(s.get(dim), (int, float))]
        return sum(v) / len(v) if v else None

    L = ["# 2026-09-21 补 12 条（按工艺域）线上实跑 + 判分", "",
         "## 一、为什么补这 12 条", "",
         "原来那 20 条只有**题型**一个分类轴（来自训练集 `family`），工艺域没落库。",
         "把 20 条按工艺域摊开后发现明显偏斜：**飞灰 12 条、炉型/燃烧 10 条，而炉渣只有 3 条、",
         "渗滤液 3 条、二噁英 4 条、监测 5 条**。本次从三个题库里按「工艺域缺口 + 题型效果好 + 有判分优先」",
         "补 12 条，并排除越界题（露天焚烧秸秆、医疗废物炉、放射性废物炉）。", "",
         "| 工艺域 | 原 20 条 | 现在 32 条 |", "| --- | --- | --- |"]
    DOM = ["飞灰", "炉渣/底渣", "烟气净化", "二噁英", "渗滤液/废水",
           "炉型/燃烧", "重金属", "监测/仪表", "资源化利用"]
    all32 = load(D / "垃圾焚烧好题型32条.jsonl")
    for d in DOM:
        o = sum(1 for r in all32 if r.get("批次") == "原 20 条" and d in (r.get("工艺域") or []))
        t = sum(1 for r in all32 if d in (r.get("工艺域") or []))
        L.append(f"| {d} | {o} | **{t}** |")

    L += ["", "## 二、12 条的实测结果", "",
          f"- 成功 **{len(rows)}/{len(rows)}**，平均 **{sum(r['耗时s'] for r in rows) / len(rows):.0f}s**、"
          f"引用 **{sum(r['引用条数'] for r in rows) / len(rows):.1f}** 条、"
          f"答案 **{sum(r['答案字数'] for r in rows) / len(rows):.0f}** 字",
          f"- rerank 顶分 {min(r['rerank_top1'] for r in rows):.3f} ～ "
          f"{max(r['rerank_top1'] for r in rows):.3f}", ""]

    if scored:
        L += ["### 判分（五维，1-5 分；口径与 20 条那次完全一致）", "",
              "| 维度 | 补 12 条 | 原 20 条（对照） |", "| --- | --- | --- |"]
        for k, cn in DIMS:
            a, b = avg(k), (avg(k, list(oldsc.values())) if oldsc else None)
            L.append(f"| {cn} | **{a:.2f}** | {b:.2f} |" if a and b else
                     f"| {cn} | {a:.2f} | — |" if a else f"| {cn} | — | — |")
        a = sum(s["均分"] for s in scored) / len(scored)
        b = (sum(s["均分"] for s in oldsc.values() if isinstance(s.get("均分"), (int, float)))
             / max(1, sum(1 for s in oldsc.values() if isinstance(s.get("均分"), (int, float)))))
        L += [f"| **均分** | **{a:.2f}** | {b:.2f} |" if b else f"| **均分** | **{a:.2f}** | — |", ""]

    L += ["### 逐条明细", "",
          "| # | 补的域 | 题型 | 耗时 | 引用 | 答案字数 | 正确 | 覆盖 | 可操作 | 有据 | 边界 | 均分 | 一句话 |",
          "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in sorted(rows, key=lambda x: x["序号"]):
        s = sc.get(r["序号"], {})
        L.append(f"| {r['序号']} | {r.get('主补域') or '—'} | {r['题型'][:10]} | {r['耗时s']:.0f}s | "
                 f"{r['引用条数']} | {r['答案字数']} | {s.get('correctness') or '—'} | "
                 f"{s.get('coverage') or '—'} | {s.get('actionability') or '—'} | "
                 f"{s.get('grounding') or '—'} | {s.get('boundary') or '—'} | "
                 f"{s.get('均分') or '—'} | {(s.get('brief') or '')[:40]} |")
    L.append("")

    # 编造指控
    fab = [(n, s) for n, s in sc.items() if s.get("fabrications")]
    L += [f"## 三、编造指控（{len(fab)}/{len(scored)} 条）", ""]
    if fab:
        for n, s in fab:
            L.append(f"- **#{n}**（{items.get(n, {}).get('主补域', '')}）")
            for f in s["fabrications"][:3]:
                L.append(f"    - {str(f)[:150]}")
    else:
        L.append("无。")
    L.append("")

    # 引用构成与"问号项"
    L += ["## 四、引用构成的客观指标", "",
          f"- 依据类（standard/law/guideline）合计 {sum(r['依据类条数'] for r in rows)} 条，"
          f"案例类（report）合计 {sum(r['案例类条数'] for r in rows)} 条",
          f"- 引用标题重复合计 {sum(r['标题重复数'] for r in rows)} 处（同一文件被引多次）", ""]
    dts = Counter()
    for r in rows:
        dts.update(r["doc_type分布"])
    L += [f"- 引用类型分布：{dict(dts.most_common())}", ""]

    # 数字可溯源
    L += ["## 五、答案里的数字能不能在引用里找到（抽查）", "",
          "| # | 答案数字个数 | 引用里找不到的 | 举例 |", "| --- | --- | --- | --- |"]
    tot_bad = 0
    for r in sorted(rows, key=lambda x: x["序号"]):
        nums = set(RE_NUM.findall(r["答案"] or ""))
        blob = " ".join(" ".join((s.get("text") or "").split()) for s in (r["引用"] or []))
        blob += " " + (r["题目"] or "")
        miss = sorted(n for n in nums if n not in blob and len(n) >= 2)
        tot_bad += len(miss)
        L.append(f"| {r['序号']} | {len(nums)} | {len(miss)} | {', '.join(miss[:6])} |")
    L += ["", f"合计找不到出处的数字 **{tot_bad}** 个（含单位换算/常识值，需人工复核）。", ""]

    OUT.write_text("\n".join(L), encoding="utf-8")
    print(f"→ {OUT.relative_to(WS)}（{len(L)} 行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
