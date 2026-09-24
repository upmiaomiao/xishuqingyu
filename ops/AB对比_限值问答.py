#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A/B 对比：同一组专业问题，在新旧两个实例上分别提问，看答案质量差异。

关注三件事：
  1. 答案里有没有出现"该标准的关键数值"（专业性的硬指标）；
  2. 引用条数与**来源去重**情况（同一文件占几个引用位）；
  3. 是否出现"材料未提供表1数值"这类因语料缺失导致的拒答。

用法：AB对比_限值问答.py --old http://127.0.0.1:8011 --new http://127.0.0.1:8012
"""
import argparse
import json
import re
import sys
import urllib.request
from collections import Counter

# (问题, [答案里应出现的数值/关键词], 说明)
QUESTIONS = [
    ("储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？",
     ["25", "95"], "油气处理装置排放限值表"),
    ("制糖工业水污染物排放标准 GB 21909-2008 规定的水污染物排放限值是多少？",
     ["100", "120", "40", "50"], "表1/表2 限值"),
    ("海水水质标准 GB 3097-1997 对第一类海水水质的要求是什么？",
     ["pH", "溶解氧"], "水质分类要求"),
    ("国家危险废物名录里，医疗废物对应的废物代码有哪些？",
     ["841-001-01", "HW01"], "危废代码表"),
    ("一般工业固体废物贮存场 I 类场的防渗要求是什么？",
     ["1.0", "0.75"], "防渗系数与厚度"),
    ("生活垃圾焚烧排污许可证申请与核发技术规范主要规定了哪些内容？",
     [], "焚烧许可规范（对照题）"),
]

REFUSE = re.compile(r"材料(中)?(未|没有)(提供|包含|给出)|未提供表|资料不足|无法给出具体")


def ask(base, q, top_k=5):
    body = json.dumps({"query": q, "top_k": top_k}).encode("utf-8")
    req = urllib.request.Request(base.rstrip("/") + "/hybrid_search", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def summarize(d):
    ans = (d.get("answer") or "").strip()
    srcs = d.get("sources") or []
    files = [s.get("source", "") for s in srcs]
    return {
        "answer": ans,
        "sources": srcs,
        "max_dup": max(Counter(files).values()) if files else 0,
        "distinct": len(set(files)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--old", default="http://127.0.0.1:8011")
    ap.add_argument("--new", default="http://127.0.0.1:8012")
    ap.add_argument("--only", type=int, default=0)
    a = ap.parse_args()

    qs = QUESTIONS[a.only - 1:a.only] if a.only else QUESTIONS
    score_old = score_new = 0
    for q, needles, note in qs:
        print("=" * 80)
        print(f"问：{q}")
        print(f"    （{note}；答案应含：{'、'.join(needles) if needles else '（对照题，无数值硬要求）'}）")
        rows = {}
        for tag, base in (("旧", a.old), ("新", a.new)):
            try:
                d = ask(base, q)
            except Exception as e:
                print(f"  [{tag}] 请求失败：{e}")
                continue
            s = summarize(d)
            rows[tag] = s
            hit = [n for n in needles if n in s["answer"]]
            miss = [n for n in needles if n not in s["answer"]]
            refuse = bool(REFUSE.search(s["answer"]))
            verdict = ("命中 " + ",".join(hit)) if hit else "未命中数值"
            print(f"  [{tag}] {verdict}"
                  f"{'  缺 ' + ','.join(miss) if miss else ''}"
                  f"{'  ⚠️拒答' if refuse else ''}"
                  f"  引用 {len(s['sources'])} 条/来源 {s['distinct']} 个"
                  f"/同一文件最多 {s['max_dup']} 条")
            print(f"       {s['answer'][:300]}")
        if needles:
            if rows.get("新") and all(n in rows["新"]["answer"] for n in needles):
                score_new += 1
            if rows.get("旧") and all(n in rows["旧"]["answer"] for n in needles):
                score_old += 1
    print("=" * 80)
    print(f"数值全部命中：旧实例 {score_old} 题 / 新实例 {score_new} 题（共 {len(qs)} 题）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
