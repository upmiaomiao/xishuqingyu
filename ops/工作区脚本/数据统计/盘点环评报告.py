#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘点本地环评报告 md：大小分布、空文件、结构样本、可提取的元数据线索。"""
import os
import re
from collections import Counter

ROOT = r"D:\项目\中节能\0911训练\extracted\环评md\md"
files = [os.path.join(ROOT, f) for f in os.listdir(ROOT) if f.lower().endswith(".md")]
files.sort()
print(f"文件数 {len(files)}")

sizes = [(os.path.getsize(p), p) for p in files]
tiny = [(s, p) for s, p in sizes if s < 2000]
print(f"小于 2KB 的文件 {len(tiny)} 份:")
for s, p in sorted(tiny)[:10]:
    print(f"   {s:6d} 字节  {os.path.basename(p)}")

print("\n大小分档:")
buckets = Counter()
for s, _ in sizes:
    if s < 2000:
        buckets["<2KB"] += 1
    elif s < 100_000:
        buckets["2KB-100KB"] += 1
    elif s < 500_000:
        buckets["100-500KB"] += 1
    elif s < 1_000_000:
        buckets["0.5-1MB"] += 1
    else:
        buckets[">1MB"] += 1
for k in ("<2KB", "2KB-100KB", "100-500KB", "0.5-1MB", ">1MB"):
    print(f"   {k:12s} {buckets[k]}")

# 结构样本：取 3 份中等大小的
mid = [p for s, p in sizes if 200_000 < s < 600_000][:3]
for p in mid:
    t = open(p, encoding="utf-8", errors="replace").read()
    print("\n" + "=" * 76)
    print(f"### {os.path.basename(p)}  {len(t):,} 字")
    print("--- 前 700 字 ---")
    print(t[:700])
    heads = re.findall(r"^#{1,3}\s*(.+)$", t, re.M)
    print(f"--- 标题数 {len(heads)}，前 12 个 ---")
    for h in heads[:12]:
        print("   ", h[:60])

# 元数据线索：常见字段出现频率（在全部文件的前 3000 字里找）
print("\n=== 元数据线索（前 3000 字内出现次数） ===")
pat = {
    "建设单位": re.compile(r"建设单位[：:]\s*(\S{2,30})"),
    "编制单位": re.compile(r"编制单位[：:]\s*(\S{2,30})"),
    "建设地点": re.compile(r"建设地点[：:]\s*(\S{2,40})"),
    "行业类别": re.compile(r"行业类别[：:]?\s*(\S{2,40})"),
    "项目名称": re.compile(r"项目名称[：:]\s*(\S{2,40})"),
    "环评单位": re.compile(r"环评单位[：:]\s*(\S{2,30})"),
}
hits = Counter()
samples = {k: [] for k in pat}
for p in files:
    try:
        head = open(p, encoding="utf-8", errors="replace").read(3000)
    except Exception:
        continue
    for k, rx in pat.items():
        m = rx.search(head)
        if m:
            hits[k] += 1
            if len(samples[k]) < 3:
                samples[k].append(m.group(1)[:34])
for k in pat:
    print(f"   {k:8s} {hits[k]:4d} 份   例: {samples[k]}")
