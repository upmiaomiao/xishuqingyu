#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B 步核心验收：新入的环评报告语料（占索引 83%）是否挤掉了标准/导则检索。

对每条问题输出 top-5 的语料分布，并标注是否命中期望语料。
判定：标准/导则类问题里，报告语料不应占据多数，且期望内容应出现在 top-5。
"""
import json
import sys

sys.path.insert(0, "/data/fagui_rag")
from retriever import Retriever  # noqa: E402

# (类别, 问题, 期望语料前缀, 答案里应出现的关键词)
CASES = [
    ("标准", "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
     "生态环境标准规范", ["渗透系数", "0.75"]),
    ("标准", "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？",
     "生态环境标准规范", ["NMHC", "25"]),
    ("导则", "大气环境影响评价的评价等级是怎么判定的？",
     "环评导则", ["Pmax", "10%"]),
    ("标准", "生活垃圾焚烧烟气中二噁英的排放限值是多少？",
     "生态环境标准规范", ["二噁英", "0.1"]),
    ("标准", "危险废物的鉴别标准是什么？",
     "生态环境标准规范", ["鉴别", "危险特性"]),
    ("法规", "未批先建的法律责任和罚款幅度",
     "生态环境法律法规", ["罚款", "责令"]),
    ("报告", "郑州市金水河综合整治工程的环境影响评价结论是什么？",
     "环评报告", []),
    ("报告", "山东管网东干线天然气管道工程的环境影响评价结论是什么？",
     "环评报告", []),
]


def main():
    r = Retriever()
    print(f"{'类别':4s} {'报告占比':8s} {'期望语料命中':12s} 问题")
    verdict = []
    for label, q, expect, needles in CASES:
        hits = r.retrieve(q, 20, 5)
        corps = [h.get("source", "").split("/")[0] for h in hits]
        rep = sum(1 for c in corps if c == "环评报告")
        exp_hit = sum(1 for c in corps if c == expect)
        text = " ".join((h.get("text") or "") for h in hits)
        nd = [n for n in needles if n not in text]
        ok = (rep <= 2 or label == "报告") and exp_hit >= 1 and not nd
        verdict.append(ok)
        print(f"\n[{label}] {q}")
        print(f"  报告语料 {rep}/5   期望语料({expect}) {exp_hit}/5   "
              f"关键内容{'齐' if not nd else '缺 ' + ','.join(nd)}  → {'通过' if ok else '不通过'}")
        for h in hits:
            src = h.get("source", "")
            print(f"    {src[:80]}")
        if label != "报告":
            print(f"    首条正文: {' '.join((hits[0].get('text') or '').split())[:120]}")
    print(f"\n合计通过 {sum(verdict)} / {len(CASES)}")


if __name__ == "__main__":
    sys.exit(main())
