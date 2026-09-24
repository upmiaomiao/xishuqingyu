#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证"按语料设上限"能否解决报告语料稀释问题（不改代码，先模拟）。

对每条问题取出重排后的 20 个候选，分别按
  (i) 现状（取前 5）
  (ii) 报告语料最多 2 条（其余名额给非报告）
选最终 5 条，比较期望内容是否出现在结果里。
"""
import sys

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever  # noqa: E402

CASES = [
    ("标准", "一般工业固体废物贮存场 I 类场的防渗要求是什么？", ["渗透系数", "0.75"]),
    ("标准", "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？", ["NMHC", "25"]),
    ("导则", "大气环境影响评价的评价等级是怎么判定的？", ["Pmax", "10%"]),
    ("标准", "生活垃圾焚烧烟气中二噁英的排放限值是多少？", ["二噁英", "0.1"]),
    ("标准", "危险废物的鉴别标准是什么？", ["鉴别", "危险特性"]),
    ("法规", "未批先建的法律责任和罚款幅度", ["罚款", "责令"]),
    ("报告", "郑州市金水河综合整治工程的环境影响评价结论是什么？", []),
    ("报告", "济宁市生活垃圾焚烧发电二期改扩建项目的环境影响结论？", []),
]
REPORT = "环评报告"


def cap_pick(hits, per_report, top_k=5):
    """报告语料最多 per_report 条，其余名额优先给非报告；名额不足再放宽。"""
    picked, skipped, rep = [], [], 0
    for h in hits:
        is_rep = h.get("source", "").startswith(REPORT)
        if is_rep and rep >= per_report:
            skipped.append(h)
            continue
        if is_rep:
            rep += 1
        picked.append(h)
        if len(picked) >= top_k:
            return picked
    picked.extend(skipped[: top_k - len(picked)])
    return picked


def describe(hits, needles):
    rep = sum(1 for h in hits if h.get("source", "").startswith(REPORT))
    text = " ".join((h.get("text") or "") for h in hits)
    miss = [n for n in needles if n not in text]
    return rep, len(hits), miss


r = Retriever()
print(f"{'类别':4s} {'现状(报告/条, 缺)':26s} {'上限2(报告/条, 缺)':26s} 问题")
better = worse = same = 0
for label, q, needles in CASES:
    cand = r.retrieve(q, 20, 20)          # 拿 20 条重排结果
    cur = cap_pick(cand, 99)              # 现状
    new = cap_pick(cand, 2)               # 报告上限 2
    rc, nc, mc = describe(cur, needles)
    rn, nn, mn = describe(new, needles)
    tag = "改善" if (len(mn) < len(mc)) else ("变差" if len(mn) > len(mc) else "持平")
    if tag == "改善":
        better += 1
    elif tag == "变差":
        worse += 1
    else:
        same += 1
    print(f"[{label}] 现状 {rc}/5 缺{','.join(mc) or '—':12s}  "
          f"上限2 {rn}/5 缺{','.join(mn) or '—':12s} {tag}  {q[:30]}")
print(f"\n改善 {better} / 持平 {same} / 变差 {worse}")
