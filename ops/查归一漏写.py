#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查清"改了文本、向量却没变"的 59/200 —— 是正常（只改空白/标点，分词后一样）还是漏写。

判定方法：把这些行的新旧文本做字符级差异分析
  · 如果差异只是空白/空括号/美元符这类"分词后等价"的改动 → 向量相同是正常的；
  · 如果差异里有数字或汉字变化，向量却一模一样 → 说明有行没写进去，是 bug。
"""
from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location(
    "tc", "/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py")
tc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tc)

V1 = np.load("/data/fagui_rag/index/vectors.npy", mmap_mode="r")
V2 = np.load("/data/fagui_rag/index_v2/vectors.npy", mmap_mode="r")

# 读旧文本
old_texts: list[str] = []
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as fh:
    for line in fh:
        old_texts.append(json.loads(line).get("text") or "")
new_texts: list[str] = []
with open("/data/fagui_rag/index_v2/chunks.jsonl", encoding="utf-8") as fh:
    for line in fh:
        new_texts.append(json.loads(line).get("text") or "")

changed = [i for i, (a, b) in enumerate(zip(old_texts, new_texts)) if a != b]
print(f"变更行 {len(changed):,} 条")

identical_vec = []
content_changed = 0
kinds = Counter()
for i in changed:
    a, b = old_texts[i], new_texts[i]
    same_vec = np.array_equal(np.asarray(V1[i]), np.asarray(V2[i]))
    # 把"去掉所有空白、括号、美元符"再比 —— 等价则说明只是排版差异
    norm_a = re.sub(r"[\s（）()\[\]【】$]", "", a)
    norm_b = re.sub(r"[\s（）()\[\]【】$]", "", b)
    if norm_a == norm_b:
        kinds["仅排版差异（分词后可能等价）"] += 1
    else:
        kinds["内容有实质变化"] += 1
        content_changed += 1
    if same_vec:
        identical_vec.append(i)

print(f"向量未变的变更行 {len(identical_vec):,} 条")
print("变更类型分布：", dict(kinds))

# 向量未变的行里，有多少是"仅排版差异"
same_vec_typo = sum(1 for i in identical_vec
                    if re.sub(r"[\s（）()\[\]【】$]", "", old_texts[i])
                    == re.sub(r"[\s（）()\[\]【】$]", "", new_texts[i]))
print(f"向量未变中『仅排版差异』{same_vec_typo:,} 条 / 共 {len(identical_vec):,} 条")

suspect = [i for i in identical_vec
           if re.sub(r"[\s（）()\[\]【】$]", "", old_texts[i])
           != re.sub(r"[\s（）()\[\]【】$]", "", new_texts[i])]
print(f"\n⚠️ 需要人工看的可疑行（内容真变了、向量却没变）：{len(suspect):,} 条")
for i in suspect[:5]:
    a, b = old_texts[i], new_texts[i]
    # 找第一个不同的位置
    k = next((j for j in range(min(len(a), len(b))) if a[j] != b[j]), min(len(a), len(b)))
    print("-" * 90)
    print(f"行 {i}  旧: …{a[max(0,k-60):k+60]!r}")
    print(f"        新: …{b[max(0,k-60):k+60]!r}")
