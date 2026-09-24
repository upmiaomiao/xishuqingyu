#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现 /doc 正向用例失败：对同一批来源逐个测 /doc，看是全部失败还是部分失败。

判定要点：
  · 若同一批来源里有的 200、有的 404 → 是"PDF 缺失"的数据问题（历史已知 14.6% 缺口）
  · 若全部 404 → 才是 /doc 通路回归
"""
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
]


def get(path, timeout=180):
    r = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode(), {}


def main():
    for q in QUERIES:
        st, b, _ = get("/hybrid_search?query=" + urllib.parse.quote(q))
        print("=" * 70)
        print("问题：%s  → HTTP %s" % (q, st))
        if st != 200:
            print("  取源失败：%s" % b[:200])
            continue
        d = json.loads(b.decode("utf-8"))
        srcs = d.get("sources") or []
        print("  route=%s  来源 %d 条" % (d.get("route"), len(srcs)))
        print("  %-4s %-6s %-46s %s" % ("#", "score", "source", "/doc"))
        for i, s in enumerate(srcs):
            src = str(s.get("source", ""))
            rs = s.get("rerank_score")
            rs = ("%.3f" % rs) if isinstance(rs, (int, float)) else "  -  "
            if src.lower().endswith(".md"):
                dst, db, dh = get("/doc?source=" + urllib.parse.quote(src), timeout=120)
                tail = "200 %s %d字节" % (dh.get("Content-Type", ""), len(db)) if dst == 200 else "%s %s" % (dst, db[:60])
            else:
                tail = "（非 .md，不走 /doc）"
            print("  %-4d %-6s %-46s %s" % (i, rs, src[-46:], tail))


if __name__ == "__main__":
    main()
