#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抽样真实提问，统计引用卡片里「查看原文 PDF」的死链比例（用户实际感受）。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"

QUERIES = [
    "生活垃圾焚烧飞灰属于危险废物吗",
    "危险废物贮存污染控制标准有哪些要求",
    "环境影响评价报告书的主要内容包括哪些",
    "垃圾焚烧发电项目的大气污染物排放限值是多少",
    "污水处理厂恶臭气体如何防治",
    "建设项目环境影响评价的分类管理是怎么规定的",
    "危废暂存间的防渗要求有哪些",
    "环评报告里大气环境影响预测采用什么模型",
]


def get(path, timeout=180):
    r = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode()


def main():
    tot_md = tot_dead = tot_kg = 0
    all_dead_queries = 0
    rows = []
    for q in QUERIES:
        st, b = get("/hybrid_search?query=" + urllib.parse.quote(q))
        if st != 200:
            rows.append((q, "取源失败 HTTP %s" % st, "", ""))
            continue
        d = json.loads(b.decode("utf-8"))
        srcs = d.get("sources") or []
        md = [s for s in srcs if str(s.get("source", "")).lower().endswith(".md")]
        kg = [s for s in srcs if not str(s.get("source", "")).lower().endswith(".md")]
        dead = 0
        for s in md:
            dst, _ = get("/doc?source=" + urllib.parse.quote(s["source"]), timeout=120)
            if dst != 200:
                dead += 1
        tot_md += len(md)
        tot_dead += dead
        tot_kg += len(kg)
        if md and dead == len(md):
            all_dead_queries += 1
        rows.append((q, "%d 条引用" % len(srcs), "%d/%d 死链" % (dead, len(md)),
                     "全死" if md and dead == len(md) else ("部分死" if dead else "全可点")))

    print("%-44s %-10s %-12s %s" % ("提问", "来源", ".md死链", "结论"))
    print("-" * 88)
    for r in rows:
        print("%-44s %-10s %-12s %s" % (r[0][:42], r[1], r[2], r[3]))
    print("-" * 88)
    print("合计：.md 引用 %d 条，其中死链 %d 条 = %.1f%%"
          % (tot_md, tot_dead, 100.0 * tot_dead / max(tot_md, 1)))
    print("      知识图谱来源 %d 条（不走 /doc）" % tot_kg)
    print("      %d/%d 个提问的引用卡片【全部】点不开" % (all_dead_queries, len(QUERIES)))


if __name__ == "__main__":
    main()
