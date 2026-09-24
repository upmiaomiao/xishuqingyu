#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把实跑 + 评分合成一份报告（markdown）。

输入：_工作记录/实跑20条_输出.jsonl、_工作记录/实跑20条_评分.jsonl
输出：_工作记录/2026-09-21-20条好题型线上实跑.md
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
D = WS / "_工作记录"
OUT = D / "2026-09-21-20条好题型线上实跑.md"

runs = {r["序号"]: r for r in
        (json.loads(l) for l in (D / "实跑20条_输出.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
sp = D / "实跑20条_评分.jsonl"
scores = {}
if sp.is_file():
    scores = {r["序号"]: r for r in
              (json.loads(l) for l in sp.read_text(encoding="utf-8").splitlines() if l.strip())}

rows = []
for no in sorted(runs):
    r, s = runs[no], scores.get(no, {})
    rows.append({
        "no": no, "题型": r["题型"], "语言": r.get("语言", "中文"),
        "耗时": r["耗时s"], "字数": r["答案字数"], "引用": r["引用条数"], "依据": r["依据类条数"],
        "正确": s.get("correctness"), "覆盖": s.get("coverage"), "可操作": s.get("actionability"),
        "有据": s.get("grounding"), "边界": s.get("boundary"), "均分": s.get("均分"),
        "编造": len(s.get("fabrications") or []), "data_gap": s.get("data_gap"),
        "answerable": s.get("answerable"), "brief": s.get("brief") or "",
        "题目标准号": r.get("题目中的标准号") or [], "引中标准号": r.get("引用里命中的标准号") or [],
        "引用来源": r.get("引用来源") or [], "题目": r["题目"],
    })

L = ["# 20 条垃圾焚烧「好题型」线上实跑（2026-09-21）", "",
     f"- 对象：`http://10.201.31.10:8011/hybrid_search`（线上站点，RAG 路线）",
     f"- 题源：`_工作记录/垃圾焚烧好题型20条.jsonl`（题型取自训练集/v5 测试判分最好的几类）",
     f"- 成功 **{sum(1 for r in rows if r['均分'] is not None or r['字数'])}/{len(rows)}**，"
     f"平均耗时 {sum(r['耗时'] for r in rows)/len(rows):.0f}s、"
     f"平均引用 {sum(r['引用'] for r in rows)/len(rows):.1f} 条、"
     f"平均答案 {sum(r['字数'] for r in rows)/len(rows):.0f} 字", ""]

sc = [r for r in rows if isinstance(r["均分"], (int, float))]
if sc:
    L += ["## 一、总评分（judge：deepseek-v4-flash-guan，1–5 分/维）", "",
          "| 维度 | 平均 |", "|---|---|"]
    for k in ("正确", "覆盖", "可操作", "有据", "边界"):
        v = [r[k] for r in sc if isinstance(r[k], (int, float))]
        if v:
            L.append(f"| {k} | **{sum(v)/len(v):.2f}** |")
    L += [f"| **均分** | **{sum(r['均分'] for r in sc)/len(sc):.2f}** |", "",
          f"编造指控 {sum(1 for r in sc if r['编造'])} 条；"
          f"judge 认为「资料不足」{sum(1 for r in sc if r['data_gap'])} 条；"
          f"judge 认为「引用里拿不到所需信息」{sum(1 for r in sc if r['answerable'] is False)} 条", ""]

L += ["## 二、逐条", "", "| # | 题型 | 语言 | 耗时 | 答案字数 | 引用(依据) | 正确 | 覆盖 | 可操作 | 有据 | 边界 | 均分 | 编造 |",
      "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    def f(v):
        return "—" if v is None else str(v)
    L.append(f"| {r['no']} | {r['题型']} | {r['语言']} | {r['耗时']:.0f}s | {r['字数']} | "
             f"{r['引用']}({r['依据']}) | {f(r['正确'])} | {f(r['覆盖'])} | {f(r['可操作'])} | "
             f"{f(r['有据'])} | {f(r['边界'])} | {f(r['均分'])} | {r['编造']} |")

L += ["", "## 三、按题型汇总", ""]
by = {}
for r in rows:
    by.setdefault(r["题型"], []).append(r)
L += ["| 题型 | 条数 | 均分 | 平均引用 | 平均字数 | judge 一句话 |", "|---|---|---|---|---|---|"]
for t, v in sorted(by.items(), key=lambda kv: -(sum(x["均分"] for x in kv[1] if isinstance(x["均分"], (int, float))) / max(1, len([x for x in kv[1] if isinstance(x["均分"], (int, float)])))):
    vv = [x["均分"] for x in v if isinstance(x["均分"], (int, float))]
    L.append(f"| {t} | {len(v)} | {sum(vv)/len(vv):.2f} | "
             f"{sum(x['引用'] for x in v)/len(v):.1f} | {sum(x['字数'] for x in v)/len(v):.0f} | "
             f"{'; '.join(x['brief'][:40] for x in v if x['brief'])[:120]} |")

L += ["", "## 四、引用命中情况（题目点名的标准号 vs 引用里的标准号）", "",
      "| # | 题目点名 | 引用命中 |", "|---|---|---|"]
for r in rows:
    L.append(f"| {r['no']} | {', '.join(r['题目标准号']) or '—'} | {', '.join(r['引中标准号']) or '—'} |")

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"→ {OUT.relative_to(WS)}")
print("\n".join(L[:40]))
