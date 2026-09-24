#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印某份报告的审核结果（项数/统计/逐项结论）。用法：show_result.py <报告名或关键词>"""
import glob
import json
import os
import sys

kw = sys.argv[1] if len(sys.argv) > 1 else ""
files = [p for p in glob.glob("/data/eia_audit/_审核结果/*.json")
         if kw in os.path.basename(p)
         and not os.path.basename(p).startswith(("gold评测",))
         and ".导出" not in os.path.basename(p)]
if not files:
    print("没有匹配的审核结果：", kw)
    sys.exit(1)
for p in files[:3]:
    d = json.load(open(p, encoding="utf-8"))
    print("==", os.path.basename(p), "项数", len(d["items"]), d.get("统计"))
    for i in d["items"]:
        print("   %-6s %-16s %-8s %s" % (i["AI审核"], i["审核项"], i["环评文件"],
                                         (i.get("理由") or "")[:70]))