#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读诊断：B5 那类问题（"GB8978 总汞 0.05 是车间口还是三级标准？"）到底卡在哪一层。

上一支探针（查依据保底.py）已经查明：**配额把 50 块权威语料放进了候选池，但最终 5 条引用全是环评报告**。
保底是"软的"（`auth_line = max(AUTH_FLOOR, 最高分 − AUTH_GAP)`，够不着就不占位），
所以还得再往下问一句：**GB 8978 自己的块，究竟在不在池子里？** 三种结局，修法完全不同：

  A. 在池子里、只是分数被报告压过去  → 检索侧的问题（保底线/权重），改代码
  B. 不在池子里（连召回都没召回）    → 查询/嵌入侧的问题，可能要查询扩展或标准号硬匹配
  C. 全库里根本没有那段文字（表格/图片没进索引）→ 数据问题，改代码没用

本脚本把三层都打出来：
  ① 全库统计：source 含 8978 的块数、其中含「第一类污染物」「车间」的块数；
  ② 该问题的候选池（recall）里，8978 的块有几条、分数排第几；
  ③ 换一个"标准原文式"的查询再召回一次，看是否只是问法的问题。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查8978在哪一层.py
"""
from __future__ import annotations

import re
import sys

sys.path.insert(0, "/data/fagui_rag")
sys.path.insert(0, "/home/test/xishu_qingyu_serve")

from xishu_pipeline.retrieve import retriever                      # noqa: E402
import retriever as R                                               # noqa: E402

Q = "GB8978总汞0.05 mg/L，是排到哪类排放口？是三级标准吗？"
Q2 = "《污水综合排放标准》第一类污染物在车间或车间处理设施排放口采样"
HI = re.compile(r"第一类污染物")
WS = re.compile(r"车间")

print("=" * 96)
print("[①] 全库：哪些块真的写了「第一类污染物…车间排放口」")
tot_8978 = tot_hi = 0
by_src: dict = {}
for i, c in enumerate(retriever.chunks):
    src = c.get("source") or ""
    txt = c.get("text") or ""
    hit_hi, hit_ws = bool(HI.search(txt)), bool(WS.search(txt))
    if hit_hi:
        tot_hi += 1
    if "8978" in src or "8978" in (c.get("title") or "") or "污水综合排放标准" in (c.get("title") or ""):
        tot_8978 += 1
        e = by_src.setdefault(src, {"n": 0, "hi": 0, "corpus": R.corpus_of(c),
                                    "status": c.get("status"), "title": c.get("title")})
        e["n"] += 1
        e["hi"] += 1 if (hit_hi and hit_ws) else 0
print("  全库含「第一类污染物」的块：%d 条" % tot_hi)
print("  GB 8978 / 污水综合排放标准 相关块：%d 条，分布在 %d 份文档" % (tot_8978, len(by_src)))
for src, e in sorted(by_src.items(), key=lambda kv: -kv[1]["n"])[:8]:
    print("     · %-22s 块 %-4d 含「第一类污染物+车间」 %-3d ｜ %s ｜ %s"
          % (e["corpus"], e["n"], e["hi"], e["status"], (e["title"] or src)[:44]))

for q in (Q, Q2):
    print("=" * 96)
    print("[②] 候选中 8978 的位置 ｜ Q：%s" % q)
    vec = retriever.embed(q)
    cands = retriever.recall(vec, top_k_vec=20)
    print("  候选池 %d 块" % len(cands))
    rank = 0
    shown = 0
    for i, s in cands:
        rank += 1
        c = retriever.chunks[i]
        src = c.get("source") or ""
        if "8978" in src or "污水综合排放标准" in (c.get("title") or ""):
            print("     · 第 %d 名 分数 %.4f ｜ %s ｜ %s ｜ %s"
                  % (rank, s, R.corpus_of(c), c.get("status"), (c.get("title") or src)[:44]))
            shown += 1
        if shown >= 6:
            break
    if not shown:
        print("     **候选池里一条 8978 的块都没有**")
    # 最终引用里有没有
    got = retriever.retrieve(q, 20, 5)
    hits = [c for c in got if "8978" in (c.get("source") or "")
            or "污水综合排放标准" in (c.get("title") or "")]
    print("  最终 5 条引用里 8978 的块：%d 条" % len(hits))
    for c in got:
        print("     [%s] %-16s %-8s %s" % ("依据" if R.is_authority(c) else "案例",
                                           R.corpus_of(c), c.get("status") or "-",
                                           (c.get("title") or c.get("source") or "")[:50]))
print("=" * 96)
print("怎么读这份结果：")
print("  · [①] 若「GB 8978 相关块」=0 或 hi=0 → 属 C（数据没进索引，改检索没用）")
print("  · [②] 若候选池里有 8978 的块但最终引用没有 → 属 A（保底线/权重问题，可改代码）")
print("  · [②] 若候选池里也没有，但换问法 Q2 能召回 → 属 B（问法/嵌入问题，可做查询扩展）")
