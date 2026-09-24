#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全索引抽样：旧清洗 vs 新清洗，量化"数值被删掉"的影响面。

回答三个问题：
  ① 语料里到底有多少片段夹带 LaTeX（$...$）？
  ② 旧清洗让多少片段**丢了数字**？新清洗救回多少？
  ③ 新清洗有没有误伤（本来没有公式的片段被改动）？
"""
from __future__ import annotations

import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

IDX = Path("/data/fagui_rag/index/chunks.jsonl")


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


old = load("/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py", "tc_old")
new = load("/data/fagui_rag/_staging/textclean_v2.py", "tc_new")

NUM = re.compile(r"\d+(?:\.\d+)?")
SUPS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺", "0123456789-+")


def digits(s: str):
    """把上标也折算成数字再比：10⁻⁵ 里的 ⁵ 是新实现"保住"的，不能算丢。"""
    return Counter(NUM.findall(s.translate(SUPS)))


total = 0
with_math = 0
old_lost_num = 0          # 旧清洗丢了数字的片段数
new_recovered = 0         # 新清洗把数字救回来的片段数
old_lost_total = 0        # 旧清洗丢掉的数字总个数
new_lost_num = 0          # 新清洗也丢了数字的片段（数字在 $ 外面却仍消失的情况）
collateral = 0            # 新清洗改动了"没有公式也没有命令"的片段（误伤）
residual_cmd = 0          # 新清洗后仍有反斜杠命令
examples = []
new_lost_examples = []
residual_examples = []
by_corpus = Counter()
by_corpus_math = Counter()

with IDX.open(encoding="utf-8") as fh:
    for line in fh:
        c = json.loads(line)
        t = c.get("text") or ""
        if not t:
            continue
        total += 1
        corpus = (c.get("source") or "").split("/")[0]
        has_math = "$" in t
        if has_math:
            with_math += 1
            by_corpus_math[corpus] += 1
        o = old.clean_retrieved_text(t)
        n = new.clean_retrieved_text(t)
        so, sn = digits(o), digits(n)
        lo = sum((so - sn).values())
        ln = sum((sn - so).values())
        if ln:
            old_lost_num += 1
            old_lost_total += ln
            by_corpus[corpus] += 1
            if len(examples) < 3:
                examples.append((c.get("source"), t[:260], o[:200], n[:200]))
        if lo:
            new_lost_num += 1
            if len(new_lost_examples) < 3:
                new_lost_examples.append((c.get("source"), t[:200], n[:200]))
        if (not has_math) and ("\\" not in t) and (o != n):
            collateral += 1
        if "\\" in n:
            residual_cmd += 1
            if len(residual_examples) < 3:
                residual_examples.append((c.get("source"), n[:200]))

print(f"① 全索引 {total:,} 个片段，夹带公式($...$)的 {with_math:,} 个 "
      f"（{with_math/total*100:.1f}%）")
print(f"   其中：环评报告 {by_corpus_math['环评报告']:,}，"
      f"生态环境标准规范 {by_corpus_math['生态环境标准规范']:,}，"
      f"生态环境法律法规 {by_corpus_math['生态环境法律法规']:,}，"
      f"环评导则 {by_corpus_math['环评导则']:,}")
print(f"\n② 旧清洗让 {old_lost_num:,} 个片段丢了数字，一共丢掉 {old_lost_total:,} 个数字")
print(f"   按语料分布：{dict(by_corpus.most_common())}")
print(f"   新清洗也丢数字的片段 {new_lost_num:,} 个（应为 0）")
print(f"\n③ 新清洗误伤（无公式无命令却被改动）{collateral:,} 个片段（应为 0）")
print(f"   新清洗后仍有反斜杠命令的 {residual_cmd:,} 个片段")

for src, a, b, cc in examples:
    print("\n" + "-" * 96)
    print("来源:", src)
    print("原文  :", re.sub(r"\s+", " ", a))
    print("旧清洗:", re.sub(r"\s+", " ", b))
    print("新清洗:", re.sub(r"\s+", " ", cc))

print("\n\n===== 新清洗仍丢数字的例子（要人工确认是不是真丢）=====")
for src, a, cc in new_lost_examples:
    print("-" * 96)
    print("来源:", src)
    print("原文:", re.sub(r"\s+", " ", a))
    print("新洗:", re.sub(r"\s+", " ", cc))

print("\n\n===== 新清洗后仍有反斜杠的例子 =====")
for src, cc in residual_examples:
    print("-" * 96)
    print("来源:", src)
    print("新洗:", re.sub(r"\s+", " ", cc))
