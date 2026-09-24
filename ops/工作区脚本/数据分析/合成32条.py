#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 20 条原题补「工艺域」标签，与补的 12 条合成一份 32 条的清单。

为什么补标签：原来只有「题型」一个分类轴（来自训练集 family），工艺域没落库。
现在两者都有：题型 = 任务类型（决定答案形态），工艺域 = 题目涉及的焚烧工艺方向
（飞灰/炉渣/烟气/渗滤液/二噁英/炉型/重金属/监测/资源化），用于看覆盖缺口。

产物：
  _工作记录/垃圾焚烧好题型32条.jsonl   ← 20 原题（补了工艺域）+ 12 补题
  _工作记录/垃圾焚烧好题型32条.md      ← 人看的版本（按题型分组，标出工艺域）
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

DOMAIN_PAT = {
    "飞灰": r"飞灰",
    "炉渣/底渣": r"炉渣|底渣|渣料|集料|熔渣",
    "烟气净化": r"脱硫|脱硝|SCR|SNCR|布袋|半干法|烟气净化|活性炭",
    "二噁英": r"二噁英|PCDD|PCDF|呋喃",
    "渗滤液/废水": r"渗滤液|渗沥液|废水|酸性废水|污水处理",
    "炉型/燃烧": r"炉排|流化床|焚烧炉|炉膛|燃烧|配风|一次风|二次风|3T\+E",
    "重金属": r"重金属|铅|镉|汞|Pb|Cd|Hg|锌|Zn|铬|砷",
    "监测/仪表": r"在线监测|CEMS|监测数据|自动监测|取样|测量|仪表|传感器|软测量|DCS|遥感|监测",
    "资源化利用": r"资源化|建材|沥青|水泥窑|协同处置|制砖|陶粒|吸附剂",
}


def load(p: Path):
    return [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]


def domains_of(text: str) -> list[str]:
    return [d for d, pat in DOMAIN_PAT.items() if re.search(pat, text, re.I)]


def main() -> int:
    old = load(D / "垃圾焚烧好题型20条.jsonl")
    new = load(D / "垃圾焚烧好题型_补12条.jsonl")
    for r in old:
        r["工艺域"] = domains_of(r["题目"])
        r["主补域"] = ""
        r["批次"] = "原 20 条"
    for r in new:
        r["批次"] = "补 12 条"
    allrows = old + new

    out = D / "垃圾焚烧好题型32条.jsonl"
    with io.open(out, "w", encoding="utf-8", newline="\n") as fh:
        for r in allrows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    dom = Counter()
    for r in allrows:
        for d in r["工艺域"]:
            dom[d] += 1
    by_type = defaultdict(list)
    for r in allrows:
        by_type[r["题型"]].append(r)

    L = ["# 垃圾焚烧「效果好」题型 32 条（20 条原题 + 12 条按工艺域补题）", "",
         "> 2026-09-21 补。**分类轴有两个**：",
         "> · **题型**（决定答案形态与判据）—— 取自训练集自带的 `family` 字段与黄金样本/专业案例的类型；",
         "> · **工艺域**（题目涉及的焚烧工艺方向）—— 本次新加的标签，用于看覆盖缺口。",
         "> 补题来源：`原始训练数据/sft3_accepted_strict_merged.jsonl`、`黄金样本/golden_judged.jsonl`、",
         "> `专业案例/专业难题展示案例.jsonl`；补题按「工艺域覆盖少 + 题型效果好 + 有判分优先」筛出，",
         "> 并排除越界题（露天焚烧秸秆、医疗废物炉、放射性废物炉）。", "",
         "## 工艺域覆盖（补题前后对比）", "",
         "| 工艺域 | 原 20 条 | 32 条合计 |", "| --- | --- | --- |"]
    for d in DOMAIN_PAT:
        o = sum(1 for r in old if d in r["工艺域"])
        t = sum(1 for r in allrows if d in r["工艺域"])
        L.append(f"| {d} | {o} | **{t}** |")
    L += ["", f"> 一条题可涉及多个域，故合计大于条数。", ""]

    for t, rs in sorted(by_type.items(), key=lambda kv: -len(kv[1])):
        L += [f"## {t}（{len(rs)} 条）", ""]
        for r in sorted(rs, key=lambda x: x["序号"]):
            mark = "　🆕补" if r["批次"] == "补 12 条" else ""
            L.append(f"**{r['序号']}.{mark}**　工艺域：`{'、'.join(r['工艺域']) or '—'}`")
            L.append("")
            L.append(r["题目"])
            L.append("")
            L.append(f"- 来源：`{r['来源']}`")
            if r.get("效果证据"):
                L.append(f"- 效果证据：{r['效果证据']}")
            L.append("")

    md = D / "垃圾焚烧好题型32条.md"
    md.write_text("\n".join(L), encoding="utf-8")
    print(f"→ {out.relative_to(WS)}（{len(allrows)} 条）")
    print(f"→ {md.relative_to(WS)}（{len(L)} 行）")
    print("\n工艺域覆盖：")
    for d in DOMAIN_PAT:
        o = sum(1 for r in old if d in r["工艺域"])
        t = sum(1 for r in allrows if d in r["工艺域"])
        print(f"  {d:<12} {o:>2} → {t:>2}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
