#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从候选里挑 12 条补题：补工艺域（炉渣、渗滤液、二噁英、监测、资源化），兼顾题型多样性。

挑选规则：
  1) 域要"中央"：该域关键词在题面里出现 ≥2 次，或出现在前 80 字（避免只是顺带提一句）；
  2) 每个题型最多 2 条（保证题型多样）；
  3) 黄金样本/专业案例带判分的优先（有实测效果证据）；
  4) 不能和现有 20 条重复（题面前 40 字比对）。
输出：_工作记录/垃圾焚烧好题型_补12条.jsonl
"""
from __future__ import annotations

import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WS = Path(__file__).resolve().parents[2]

# 目标域 → 要补几条
WANT = {"炉渣/底渣": 3, "渗滤液/废水": 2, "二噁英": 2,
        "监测/仪表": 2, "资源化利用": 2, "烟气净化": 1}

# 题型 → 效果证据（沿用 20 条那份的题型级证据，来源一致）
EVID = {
    "patent_innovation_and_comparison": "v5 焚烧测试 专利创新 4/5",
    "trend_and_gap_analysis": "v5 焚烧测试 趋势差距 5/5",
    "standard_policy_interpretation": "v5 焚烧测试 标准政策解读 5/5",
    "structured_drafting": "v5 焚烧测试 结构化撰写 3/5",
    "paper_translation_and_digest": "v5 焚烧测试 技术摘要 3+/5；黄金样本 wte_zh 22.9/25",
}
DOMAIN_PAT = {
    "炉渣/底渣": r"炉渣|底渣|渣料|集料|熔渣",
    "渗滤液/废水": r"渗滤液|废水|渗沥液|酸性废水",
    "二噁英": r"二噁英|PCDD|PCDF|呋喃",
    "监测/仪表": r"在线监测|CEMS|取样|测量|仪表|传感器|软测量|DCS|遥感|监测",
    "资源化利用": r"资源化|建材|沥青|水泥窑|协同处置|制砖|陶粒|吸附剂",
    "烟气净化": r"脱硫|脱硝|SCR|SNCR|布袋|半干法|烟气净化|活性炭",
    "飞灰": r"飞灰",
    "炉型/燃烧": r"炉排|流化床|焚烧炉|炉膛|燃烧|配风|一次风|二次风",
    "重金属": r"重金属|铅|镉|汞|Pb|Cd|Hg|锌|Zn|铬|砷",
}
FAM_CN = {
    "patent_innovation_and_comparison": "专利创新与对比",
    "trend_and_gap_analysis": "趋势与差距分析",
    "standard_policy_interpretation": "标准/政策解读",
    "structured_drafting": "结构化撰写（方案/培训/框架）",
    "paper_translation_and_digest": "技术摘要与提炼",
    "wte_zh": "专业研判（黄金样本 wte_zh）",
    "wte_en/regulatory": "合规审查（黄金样本 wte_en）",
    "wte_en/field": "现场运行与故障诊断（黄金样本 wte_en）",
}


def is_central(text: str, dom: str) -> bool:
    pat = DOMAIN_PAT[dom]
    head = text[:300]
    # 范围闸门：题面前 300 字必须落在生活垃圾焚烧发电上（挡住露天焚烧秸秆、医疗废物炉、放射性废物炉）
    if not re.search(r"生活垃圾焚烧|垃圾焚烧发电|垃圾焚烧厂|生活垃圾焚烧炉|焚烧发电|垃圾焚烧炉", head):
        return False
    if re.search(r"露天焚烧|秸秆|医疗废物|医疗废弃|放射性", head) \
            and not re.search(r"生活垃圾焚烧|垃圾焚烧发电", head):
        return False
    if dom == "监测/仪表" and not re.search(
            r"在线监测|CEMS|监测数据|自动监测|取样|测量|仪表|传感器|软测量|DCS|遥感", text):
        return False
    hits = re.findall(pat, text, re.I)
    if len(hits) >= 2:
        return True
    m = re.search(pat, text[:80], re.I)
    return bool(m)


def main() -> int:
    cands = json.loads((WS / "_中间产物" / "补题候选.json").read_text(encoding="utf-8"))
    have = [json.loads(l) for l in
            io.open(WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl", encoding="utf-8") if l.strip()]
    have_keys = {r["题目"][:40] for r in have}

    # 候选排序：黄金/案例带判分的优先，其次题面更长的（信息更全）
    def rank(c: dict) -> tuple:
        j = c.get("判分") or {}
        scored = 1 if (j.get("总分") or j.get("score")) else 0
        return (-scored, -min(len(c["题面"]), 1200))

    cands = [c for c in cands if c["题面"][:40] not in have_keys]
    cands.sort(key=rank)

    picked, fam_used, dom_used = [], Counter(), Counter()
    seen_txt = set()
    for dom, need in WANT.items():
        for c in cands:
            if dom_used[dom] >= need or len(picked) >= 12:
                break
            if c["序号"] in {p["序号"] for p in picked}:
                continue
            if c["题面"][:40] in seen_txt:      # 补题之间也不许重题
                continue
            if dom not in c["工艺域"] or not is_central(c["题面"], dom):
                continue
            fam = c["family"]
            if fam_used[fam] >= 2:
                continue
            picked.append(c)
            seen_txt.add(c["题面"][:40])
            fam_used[fam] += 1
            dom_used[dom] += 1
            c["_主域"] = dom

    print(f"选出 {len(picked)} 条：\n")
    out = []
    for i, c in enumerate(picked, start=21):
        doms = c["工艺域"]
        j = c.get("判分")
        ev = EVID.get(c["family"], "")
        if j:
            sc = j.get("总分") or j.get("score")
            ev = (ev + "；" if ev else "") + f"已有判分 {sc}"
        rec = {
            "序号": i,
            "题型": FAM_CN.get(c["family"], c["family"]),
            "工艺域": doms,
            "主补域": c["_主域"],
            "题目": c["题面"],
            "来源": f"{c['库']} {c['序号']} · family={c['family']}",
            "效果证据": ev,
            "语言": "中文",
        }
        out.append(rec)
        print(f"{i}. 【补 {c['_主域']}】{rec['题型']}  ({c['库']} {c['序号']})")
        print(f"   域：{','.join(doms)}")
        print(f"   证据：{ev}")
        print(f"   {c['题面'][:150]}…\n")

    p = WS / "_工作记录" / "垃圾焚烧好题型_补12条.jsonl"
    with io.open(p, "w", encoding="utf-8", newline="\n") as fh:
        for r in out:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"→ {p.relative_to(WS)}")
    print(f"\n题型分布：{dict(Counter(r['题型'] for r in out))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
