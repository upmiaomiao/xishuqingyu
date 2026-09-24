#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""焚烧类标准的"本体是否存在" + 元数据缺口盘点。

输出：
  1) 含 18484 / 危险废物焚烧污染控制标准 的块，按 title 归类（本体 or 转述）
  2) 全索引 doc_type 缺失比例；缺失的那些按 source 顶层目录归类
  3) 无辨识度标题（如"环境影响报告书""进行环境影响评价并公示…"）的块数
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")
SUSPECT = ("环境影响报告书", "进行环境影响评价并公示", "工程咨询证书编号")


def scan():
    n = 0
    dt = Counter()
    src_of_missing = Counter()
    bad_title = Counter()
    nan_title = Counter()
    std18484 = []
    with IDX.open(encoding="utf-8") as f:
        for line in f:
            n += 1
            try:
                d = json.loads(line)
            except Exception:
                continue
            t = d.get("doc_type")
            dt[t or "（缺）"] += 1
            if not t:
                src_of_missing[(d.get("source") or "?").split("/")[0]] += 1
            raw_ti = d.get("title")
            if not isinstance(raw_ti, str):        # 索引里真的有 NaN 标题
                nan_title[type(raw_ti).__name__] += 1
                ti = ""
            else:
                ti = raw_ti
            for s in SUSPECT:
                if ti.startswith(s) or ti == s:
                    bad_title[ti[:50]] += 1
                    break
            if "18484" in line or "危险废物焚烧污染控制标准" in line:
                std18484.append(d)
    return n, dt, src_of_missing, bad_title, std18484, nan_title


n, dt, src_of_missing, bad_title, h84, nan_title = scan()
print(f"索引总块数：{n}")
print("\n【1】doc_type 分布：")
for k, v in dt.most_common():
    print(f"   {v:>7}  {k}  ({v/n*100:.1f}%)")
print("\n【2】doc_type 缺失的块，按 source 顶层目录：")
for k, v in src_of_missing.most_common(10):
    print(f"   {v:>7}  {k}")
print(f"\n【2b】title 不是字符串（NaN/None）的块：{dict(nan_title)}")

print(f"\n【3】含 18484 / 危险废物焚烧污染控制标准 的块：{len(h84)}")
print("   按 title（前 12）：")
for t, c in Counter(d.get("title") or "?" for d in h84).most_common(12):
    print(f"     {c:>5}  {t[:80]}")
own84 = [d for d in h84 if "危险废物焚烧污染控制标准" in (d.get("title") or "")]
print(f"   标题含该标准名的块：{len(own84)}")

print("\n【4】无辨识度标题的块数（标题以这些开头）：")
for t, c in bad_title.most_common(12):
    print(f"   {c:>7}  {t}")
print(f"   合计 {sum(bad_title.values())} 块")
