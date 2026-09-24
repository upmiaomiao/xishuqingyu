#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正版盘点：chunks.jsonl 的字段叫 type（接口才映射成 doc_type）。

产出：
  1) 单块字段结构
  2) type 分布
  3) 焚烧类标准（GB 18485 / GB 18484）在语料里的"本体 vs 转述"判定
  4) 无辨识度标题数量、title 缺失数量
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")
SUSPECT = ("环境影响报告书", "进行环境影响评价并公示", "工程咨询证书编号", "一、建设项目基本情况")

n = 0
types = Counter()
statuses = Counter()
bad_title = Counter()
bad_title_by_type = Counter()
title_missing = 0
first_keys = None
h85 = []
h84 = []
own85 = own84 = 0

with IDX.open(encoding="utf-8") as f:
    for line in f:
        n += 1
        try:
            d = json.loads(line)
        except Exception:
            continue
        if first_keys is None:
            first_keys = list(d.keys())
        t = d.get("type") or "（缺）"
        types[t] += 1
        statuses[d.get("status") or "（缺）"] += 1
        raw_ti = d.get("title")
        ti = raw_ti if isinstance(raw_ti, str) else ""
        if not ti:
            title_missing += 1
        for s in SUSPECT:
            if ti.startswith(s):
                bad_title[ti[:46]] += 1
                bad_title_by_type[t] += 1
                break
        if "18485" in line or "生活垃圾焚烧污染控制标准" in line:
            h85.append(d)
            if "生活垃圾焚烧污染控制标准" in ti:
                own85 += 1
        if "18484" in line or "危险废物焚烧污染控制标准" in line:
            h84.append(d)
            if "危险废物焚烧污染控制标准" in ti:
                own84 += 1

print("【0】单块字段：", first_keys)
print(f"\n【1】type 分布（{n} 块）：")
for k, v in types.most_common():
    print(f"   {v:>7}  {k}   ({v/n*100:.1f}%)")
print(f"\n【2】status 分布：{dict(statuses.most_common(8))}")
print(f"   title 为空的块：{title_missing}（{title_missing/n*100:.2f}%）")

print(f"\n【3】GB 18485 / 生活垃圾焚烧污染控制标准：命中 {len(h85)} 块，"
      f"其中标题含标准名的（=本体）{own85} 块")
print("   命中块的 type 分布：", dict(Counter(d.get('type') or '（缺）' for d in h85)))
print("   命中块的标题（前 8）：")
for k, v in Counter(d.get("title") if isinstance(d.get("title"), str) else "（无标题）"
                    for d in h85).most_common(8):
    print(f"     {v:>5}  {k[:76]}")

print(f"\n【4】GB 18484 / 危险废物焚烧污染控制标准：命中 {len(h84)} 块，本体 {own84} 块")
print("   命中块的 type 分布：", dict(Counter(d.get('type') or '（缺）' for d in h84)))

print("\n【5】无辨识度标题：")
for k, v in bad_title.most_common(10):
    print(f"   {v:>7}  {k}")
print(f"   合计 {sum(bad_title.values())} 块；按 type：{dict(bad_title_by_type)}")
