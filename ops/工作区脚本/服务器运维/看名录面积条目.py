#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把名录里带面积阈值的条目**原样**打出来（含全部键名），用于判断"亩"系数错位到底影响哪些条目。

关键判断（本脚本要回答的）：判断双方是否**同单位** ——
  · 名录条目的阈值单位与项目填报单位**相同**（都写"亩"）⇒ 系数错位在两边**同时**发生，比较结果反而不变；
  · 只有**跨单位**比较（条目写"平方米"、项目填"亩"）才会被 666.7 倍放大。
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

p = Path(sys.argv[1] if len(sys.argv) > 1 else r"判据库\分类管理名录2021.json")
d = json.load(io.open(p, encoding="utf-8"))
items = d if isinstance(d, list) else (d.get("条目") or d.get("items") or [])
print("顶层键：%s" % (list(d) if isinstance(d, dict) else "（列表）"))
print("第一条的全部键：%s" % (list(items[0]) if items else "无"))
print()
hit = 0
for i, it in enumerate(items):
    t = json.dumps(it, ensure_ascii=False)
    if re.search(r"亩|平方米", t):
        hit += 1
        print("=" * 90)
        print("第 %d 条：" % i)
        print(json.dumps(it, ensure_ascii=False, indent=1)[:1400])
print("\n共 %d 条命中（总条目 %d）" % (hit, len(items)))
