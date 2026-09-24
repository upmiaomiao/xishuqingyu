#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看回填报告：按状态汇总，并列出明细。用法：看看.py /tmp/probe.json [条数]"""
import json
import sys
from collections import Counter

path = sys.argv[1]
n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
d = json.load(open(path, encoding="utf-8"))
c = Counter(x["status"] for x in d)
print("状态汇总:", dict(c))
reasons = Counter(x.get("reason", "") for x in d if x["status"] != "ok")
for r, k in reasons.most_common(8):
    print(f"  跳过原因 x{k}: {r[:110]}")
print()
ok = [x for x in d if x["status"] == "ok"]
ok.sort(key=lambda x: -x.get("added", 0))
print(f"回填成功的前 {min(n,len(ok))} 份:")
for x in ok[:n]:
    print(f"  +{x.get('added',0):6,d} 字  槽位 {x.get('filled')}/{x.get('refs')} "
          f"({x.get('skipped')} 未填)  {x['rel'][:66]}")
print()
skip = [x for x in d if x["status"] != "ok"]
print(f"跳过的前 {min(n,len(skip))} 份:")
for x in skip[:n]:
    print(f"  {x.get('reason','')[:40]:42s} {x['rel'][:70]}")
