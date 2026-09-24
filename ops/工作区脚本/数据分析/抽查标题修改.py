#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽查标题修改清单：改得对不对（本地分析，快速迭代规则）。"""
from __future__ import annotations

import random
import re
import sys
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
TSV = WS / "_工作记录" / "_标题修改清单_20260921.tsv"

rows = []
for line in TSV.read_text(encoding="utf-8").splitlines()[1:]:
    parts = line.split("\t")
    if len(parts) == 4:
        rows.append(parts)

print(f"清单 {len(rows)} 条")
print("原因分布：", dict(Counter(r[1] for r in rows).most_common()))

BAD_NEW = ("看图王", "pdf", "PDF", "压缩版", "W0", ".txt", "_", "未命名", "copy", "最终")
suspect = [r for r in rows if any(b in r[3] for b in BAD_NEW) or len(r[3]) < 6]
print(f"\n新标题里疑似仍有噪声/过短的：{len(suspect)} 条（{len(suspect)/len(rows)*100:.1f}%）")
for r in suspect[:12]:
    print(f"   [{r[1][:16]}] {r[2][:28]} → {r[3][:60]}")

print("\n新标题只是「原标题 + 后缀词」的：", end=" ")
SUF = re.compile(r"^(验收|竣工|环境影响|环评|报告|公示|全本|文本|文件|监测|评估|调查|书|表|稿)")
n_suf = [r for r in rows if r[3].replace(" ", "").startswith(r[2].replace(" ", ""))
         and SUF.match(r[3].replace(" ", "")[len(r[2].replace(" ", "")):] or "x")]
print(f"{len(n_suf)} 条")
for r in n_suf[:8]:
    print(f"   {r[2][:30]} → {r[3][:62]}")

random.seed(7)
print("\n「被截断」类随机 20 条：")
trunc = [r for r in rows if r[1].startswith("被截断")]
for r in random.sample(trunc, min(20, len(trunc))):
    extra = r[3].replace(r[2], "", 1)
    print(f"   旧：{r[2][:44]}")
    print(f"   新：{r[3][:64]}    （多出来的部分：{extra[:30]}）")
    print()
