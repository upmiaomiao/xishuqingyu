#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读探针：题面含标准号时，**依据保底**到底有没有把权威语料的原文补进引用位。

为什么查这个（B5 的表现很反常）：B5 的问题里明明写着「GB8978」，
`auth_need()` 应当返回 AUTH_MIN_STRICT(=3) —— 也就是 5 个引用位里应保底 3 条
来自权威语料（生态环境标准规范/法律法规/环评导则）。可实测引用 **5 条全是环评报告**。
要么保底没触发，要么候选池里根本没有可补的权威块。这两种原因的修法完全不同：
  · 没触发 → 代码/环境问题（配额被关、改写把标准号丢了…）
  · 没候选 → 是语料/切块问题（GB 8978 表1/表4 是图片或表格，正文里没有可检索的段落）
所以必须把中间过程打出来，不能只看最终引用。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查依据保底.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/data/fagui_rag")        # 检索器本体在这里（站点也是这么挂的）
sys.path.insert(0, "/home/test/xishu_qingyu_serve")

from xishu_pipeline.retrieve import retriever                      # noqa: E402
import retriever as R                                               # noqa: E402  （同一个模块对象）

Q = "GB8978总汞0.05 mg/L，是排到哪类排放口？是三级标准吗？"
Q2 = "环境空气质量标准 GB 3095 里 PM10 年平均二级浓度限值是多少？"

print("=" * 96)
print("索引目录：", getattr(retriever, "index_dir", "?"))
print("语料配额：", "开启" if getattr(retriever, "quota", None) else "关闭")
print("AUTH_MIN_STRICT =", R.AUTH_MIN_STRICT)
print("AUTHORITY_CORPORA =", R.AUTHORITY_CORPORA)

for q in (Q, Q2):
    print("=" * 96)
    print("Q：%s" % q)
    print("  RE_STD_CODE 命中：%s ｜ auth_need = %d"
          % (bool(R.RE_STD_CODE.search(q)), R.auth_need(q)))
    # 直接看召回池里有几块权威语料（不经过配额挑选）
    try:
        vec = retriever.embed(q)
        cands_raw = retriever.recall(vec, top_k_vec=20)      # 走配额的那条路（含邻块扩展）
    except Exception as exc:                                        # noqa: BLE001
        print("  检索失败：%s" % exc)
        continue
    # recall()/search() 返回 (下标, 分数) —— 块要从 retriever.chunks 取
    cands = [retriever.chunks[i] for i, _ in cands_raw]
    from collections import Counter
    corp = Counter(R.corpus_of(c) for c in cands)
    print("  召回前 20 块的语料分布：%s" % dict(corp))
    auth_in_cands = [c for c in cands if R.is_authority(c)]
    print("  其中权威语料块：%d 块" % len(auth_in_cands))
    for c in auth_in_cands[:5]:
        print("     · %-14s %s ｜ %s" % (R.corpus_of(c), (c.get("status") or "-"),
                                        (c.get("title") or "")[:52]))
    # 再看最终 5 条引用
    got = retriever.retrieve(q, 20, 5)
    print("  最终 %d 条引用：" % len(got))
    for i, c in enumerate(got, 1):
        print("     [%d] %-8s %-14s %-8s %s" % (
            i, "依据" if R.is_authority(c) else "案例", R.corpus_of(c),
            c.get("status") or "-", (c.get("title") or c.get("source") or "")[:56]))
    n_auth = sum(1 for c in got if R.is_authority(c))
    print("  → 最终权威块 %d 条 / 应保底 %d 条：%s"
          % (n_auth, R.auth_need(q),
             "达标" if n_auth >= min(R.auth_need(q), len(got)) else "**没达标**"))
print("=" * 96)
