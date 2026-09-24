# -*- coding: utf-8 -*-
"""侦察：① 标准语料里"行业专属"文档的分布 ② HJ 1408 的 source/title 长什么样
③ 环评报告语料的位置。只读，不改任何东西。"""
import collections
import json
import re

IDX = "/data/fagui_rag/index/chunks.jsonl"

RE_IND = re.compile(
    r"钢铁|烧结|球团|炼铁|炼钢|炼焦|焦化|火电|燃煤|水泥|玻璃|陶瓷|造纸|印染|制药|电镀|"
    r"有色金属|铅锌|铜镍钴|石化|石油|化工|农药|制糖|味精|啤酒|纺织|制革|涂装|汽修"
)

CIRC = re.compile(r"生活垃圾|焚烧")

std_total = 0
ind_hits = collections.Counter()
ind_docs = collections.Counter()
rep_total = 0
corpus_cnt = collections.Counter()
doc_title = {}

for line in open(IDX, encoding="utf-8"):
    c = json.loads(line)
    src = c.get("source") or ""
    corpus = src.split("/")[0]
    corpus_cnt[corpus] += 1
    if corpus == "生态环境标准规范":
        std_total += 1
        t = (c.get("title") or "") + " " + src
        for m in RE_IND.finditer(t):
            ind_hits[m.group(0)] += 1
            ind_docs[m.group(0) + " | " + src] += 1
    if "HJ 1408" in src or "HJ 1408" in (c.get("title") or ""):
        doc_title[src] = c.get("title")

print("语料块数：", dict(corpus_cnt))
print("标准块：", std_total, " 命中行业词：", sum(ind_hits.values()))
print("行业词频：", ind_hits.most_common(25))
print()
print("命中行业词最多的 15 份文档：")
for k, v in ind_docs.most_common(15):
    print("  %5d  %s" % (v, k))
print()
print("HJ 1408 相关 source/title 组合：")
for k, v in list(doc_title.items())[:10]:
    print("  source=%s | title=%s" % (k, v))
