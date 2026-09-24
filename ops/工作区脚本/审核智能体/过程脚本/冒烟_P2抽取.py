#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2 抽取层冒烟：对 8 份报告抽事实，重点看**每项是否带得住页码与原文**。

机械校验（防编造三查之一）：
  每条事实的 `原文` 必须能在它自称的那一页原文里检索到 —— 抽不到就是假的。
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）
sys.path.insert(0, BASE)
from audit.extract import extract_all, map_to_catalog_terms  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

ROOT = r"D:\项目\中节能\0911训练\环评报告\环评报告\环评报告"
CACHE = os.path.join(BASE, "_cache")


def verify_quote(rep, page, quote) -> bool:
    """原文核验：把 quote 去空白后，必须在该页文本里找到（前 30 字足够定位）。"""
    if not page or not quote:
        return False
    txt = re.sub(r"\s+", "", rep.page_text[page - 1])
    q = re.sub(r"\s+", "", quote)
    return q[:30] in txt or q[-30:] in txt


def main():
    names = sorted(f for f in os.listdir(ROOT) if f.lower().endswith(".pdf"))
    bad_total = checked_total = 0
    for name in names:
        rep = load_or_parse(os.path.join(ROOT, name), cache_dir=CACHE)
        print(f"\n=== {name[:52]}")
        ex = extract_all(rep, verbose=True)
        b = ex.basic
        for k in ("项目名称", "环评文件类型", "行业类别", "建设单位", "建设地点"):
            f = b.get(k)
            print(f"    {k}: {f.value if f else None}"
                  + (f"  (P{f.page})" if f and f.page else ""))
        if ex.materials:
            print("    物料前 6：")
            for m in ex.materials[:6]:
                print(f"      {m['名称'][:16]:18s} {m['数量']} {m['单位']:8s} P{m['页码']}")
        mp = map_to_catalog_terms(ex.materials)
        print(f"    名录用语归属："
              + (", ".join(f"{k} {v['total']:g}{v['unit']}" for k, v in mp["buckets"].items())
                 or "无"))
        print(f"    未归属 {len(mp['unmapped'])} 项，示例："
              + "; ".join(f"{u['名称'][:12]}→{u['why'][:26]}" for u in mp["unmapped"][:3]))
        if ex.risk_materials:
            print(f"    风险物质 {len(ex.risk_materials)} 项，前 3：")
            for r in ex.risk_materials[:3]:
                print(f"      {r['名称'][:14]:16s} 贮存量={r['最大贮存量t']} "
                      f"临界量={r['临界量t']} P{r['页码']}")
        if ex.sensitive_targets:
            near = [t for t in ex.sensitive_targets if (t["距离m"] or 1e9) <= 500]
            print(f"    敏感目标 {len(ex.sensitive_targets)} 项，其中 ≤500m {len(near)} 项"
                  + (f"，最近：{near[0]['名称']} {near[0]['距离m']}m P{near[0]['页码']}" if near else ""))
        print("    判据输入推导：")
        for k, v in ex.special_inputs.items():
            if v:
                print(f"      [✓] {k} = {str(v['value'])[:40]}  (P{v['page']})")
            else:
                print(f"      [ ] {k} = 未推导出")

        # ---- 原文核验（防编造三查之一）----
        items = []
        for f in ex.basic.values():
            if f and f.page and f.quote:
                items.append((f.page, f.quote))
        for m in ex.materials + ex.risk_materials + ex.sensitive_targets:
            if m.get("页码") and m.get("原文"):
                items.append((m["页码"], m["原文"]))
        for v in ex.special_inputs.values():
            if v and v.get("page") and v.get("quote"):
                items.append((v["page"], v["quote"]))
        bad = [(p, q[:40]) for p, q in items if not verify_quote(rep, p, q)]
        checked_total += len(items)
        bad_total += len(bad)
        print(f"    原文核验：{len(items) - len(bad)}/{len(items)} 可回溯"
              + (f"，不可回溯 {bad[:3]}" if bad else " ✅"))
    print(f"\n==== 合计核验 {checked_total} 条，不可回溯 {bad_total} 条 ====")
    return 1 if bad_total else 0


if __name__ == "__main__":
    sys.exit(main())