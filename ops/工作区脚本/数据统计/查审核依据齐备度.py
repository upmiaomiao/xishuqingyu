#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核智能体的参考依据在库里齐不齐：名录/指南/导则的正文与表格。

判定要点：这类依据的价值在**表格与阈值**（如"年用溶剂型胶粘剂10吨及以上"），
所以除了字数，还要看有没有 markdown 表格、有没有图片死链（表格丢失的信号）。
"""
import os
import re

BUNDLE = "/data/fagui_rag/okf_bundles"
KEYS = [
    ("分类管理名录", r"建设项目环境影响评价分类管理名录|分类管理名录"),
    ("报告表编制技术指南", r"报告表编制技术指南|编制技术指南"),
    ("有毒有害大气污染物名录", r"有毒有害大气污染物名录"),
    ("报告书编制技术指南", r"报告书编制技术指南"),
    ("总纲/各要素导则正文", r"环境影响评价技术导则"),
    ("排污许可技术规范", r"排污许可证申请与核发技术规范"),
    ("危险废物名录", r"国家危险废物名录"),
]
IMG_RE = re.compile(r"!\[\]\(images/")


def walk():
    for dp, _dn, fn in os.walk(BUNDLE):
        for f in fn:
            if f.endswith(".md"):
                yield os.path.join(dp, f)


docs = list(walk())
print(f"bundle 内 md 总数 {len(docs)}\n")
for label, rx in KEYS:
    pat = re.compile(rx)
    hits = []
    for p in docs:
        name = os.path.basename(p)
        if not pat.search(name):
            continue
        try:
            t = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(p, BUNDLE)
        n_tab = t.count("| --- |")
        n_img = len(IMG_RE.findall(t))
        hits.append((len(t), n_tab, n_img, rel))
    hits.sort(reverse=True)
    print(f"=== {label}: {len(hits)} 份")
    for chars, n_tab, n_img, rel in hits[:4]:
        flag = ""
        if n_img:
            flag += f"  ⚠图片死链 {n_img} 处"
        print(f"    {chars:7,d} 字  表格 {n_tab:3d} 张{flag}  {rel[:86]}")
    if not hits:
        print("    （库里没有）")
    print()
