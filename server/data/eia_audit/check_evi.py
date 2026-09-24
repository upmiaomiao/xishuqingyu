#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查某份报告某项审核的证据是否**真的支撑结论**（打印输入、证据、原文核验结果）。"""
import json
import os
import sys

sys.path.insert(0, "/data/eia_audit")
from audit.parse import load_or_parse          # noqa: E402
from audit.llm import quote_in_page            # noqa: E402
from audit.runner import cache_dir, report_dir  # noqa: E402

name = sys.argv[1]
key = sys.argv[2] if len(sys.argv) > 2 else "地下水"
rep = load_or_parse(os.path.join(report_dir(), name), cache_dir=cache_dir())
print("页数", rep.pages, "字符", sum(len(p) for p in rep.page_text))

# 该问题的判据输入
import glob                                        # noqa: E402
for p in glob.glob("/data/eia_audit/_审核结果/*.json"):
    d = json.load(open(p, encoding="utf-8"))
    if name[:12] not in os.path.basename(p):
        continue
    for it in d["items"]:
        if key not in it["审核项"]:
            continue
        print("===", it["审核项"], it["AI审核"], it["环评文件"])
        print("理由:", it["理由"])
        print("判据输入:", json.dumps(it["判据轨迹"].get("判据输入", {}), ensure_ascii=False)[:400])
        for e in it["证据"]:
            q = e.get("quote", "")
            onpage = quote_in_page(rep, e["page"], q)
            print("  证据 P%s 来源=%s 该页可核验=%s" % (e["page"], e.get("source"), onpage))
            print("     ", q[:150])
print("--- 全报告检索关键词 ---")
for pat in ("集中式饮用水", "特殊地下水资源", "温泉"):
    print(pat, [h["page"] for h in rep.search(pat, max_hits=5, ctx=0)])