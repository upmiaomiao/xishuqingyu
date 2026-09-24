#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 步验收：问线上 8011 环评导则问题，检查答案是否用上了导则正文的判据数值。"""
import json
import urllib.request

BASE = "http://127.0.0.1:8011"

# (问题, 答案里应出现的关键判据/数值, 说明)
CASES = [
    ("大气环境影响评价的评价等级是如何判定的？",
     ["Pmax", "10%"], "HJ 2.2-2018 表2 评价等级判别表"),
    ("地下水环境影响评价中，Ⅰ类建设项目评价等级怎么判定？",
     ["Ⅰ类", "等级"], "HJ 610-2016 评价等级判定"),
    ("土壤环境影响评价的评价等级如何划分？",
     ["敏感", "等级"], "HJ 964-2018 评价等级"),
    ("环境影响评价的工作程序包括哪些阶段？",
     ["第一阶段", "第二阶段"], "HJ 2.1-2016 总纲 工作程序"),
]


def ask(q):
    body = json.dumps({"query": q, "top_k": 5}).encode()
    req = urllib.request.Request(BASE + "/hybrid_search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


ok = 0
for q, needles, note in CASES:
    print("=" * 76)
    print(f"问：{q}\n    （{note}；应含：{'、'.join(needles)}）")
    try:
        d = ask(q)
    except Exception as e:
        print(f"  请求失败：{e}")
        continue
    ans = d.get("answer") or ""
    srcs = d.get("sources") or []
    hit = [n for n in needles if n in ans]
    print(f"  引用 {len(srcs)} 条，来源：")
    for s in srcs[:5]:
        print(f"    - {s.get('title','')[:40]} | {s.get('source','')[:70]}")
    got = len(hit) == len(needles)
    ok += 1 if got else 0
    print(f"  {'命中' if got else '缺 ' + ','.join(n for n in needles if n not in ans)}")
    print(f"  答案前 300 字：{ans[:300]}")

print("=" * 76)
print(f"导则判据命中：{ok} / {len(CASES)}")
