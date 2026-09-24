#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查 /kg/stats 并发为什么会超时。

背景：全量测试里「并发 8 次 GET /kg/stats → 全部 200」报 7/8、总耗时 3.02s。
基准是 252/1，所以这是新出现的失败，必须查清是真慢还是抖动。

/kg/stats 的实现是 `async def` 里**同步**调 load_knowledge_graph()：
    graph = load_knowledge_graph()
    labels = Counter(node.get("label") ...)
缓存在 _kg_cache 里，正常应该很便宜。所以要么是缓存没生效（每次重读 JSON），
要么是事件循环被别的东西堵住了。下面分开量：单发延迟、并发延迟、以及
有没有"第一次特别慢"的现象。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import time
import urllib.request

BASE = "http://10.201.31.10:8011"


def hit(path: str) -> tuple[int, float]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as r:
            r.read()
            return r.status, time.time() - t0
    except Exception as e:                                        # noqa: BLE001
        return -1, time.time() - t0


print("=" * 92)
print("① 单发延迟（连续 10 次）")
print("=" * 92)
times = []
for i in range(10):
    st, dt = hit("/kg/stats")
    times.append(dt)
    print("  第 %2d 次  status=%-4s  %.3fs" % (i + 1, st, dt))
print("  最快 %.3fs  最慢 %.3fs  中位 %.3fs" % (min(times), max(times), sorted(times)[5]))

print()
print("=" * 92)
print("② 并发 8 次，跑 6 轮（看是否稳定复现）")
print("=" * 92)
for rd in range(6):
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(hit, ["/kg/stats"] * 8))
    ok = sum(1 for s, _ in res if s == 200)
    slow = max(d for _, d in res)
    print("  第 %d 轮：%d/8 个 200　总 %.2fs　最慢单个 %.3fs"
          % (rd + 1, ok, time.time() - t0, slow))

print()
print("=" * 92)
print("③ 对照：并发 8 次 /health（几乎不做事）")
print("=" * 92)
for rd in range(3):
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(hit, ["/health"] * 8))
    ok = sum(1 for s, _ in res if s == 200)
    print("  第 %d 轮：%d/8 个 200　总 %.2fs　最慢单个 %.3fs"
          % (rd + 1, ok, time.time() - t0, max(d for _, d in res)))

print()
print("=" * 92)
print("④ 对照：并发 8 次 /kg/search（同样读图谱，但走了 to_thread）")
print("=" * 92)
for rd in range(3):
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(hit, ["/kg/search?query=%E5%8D%B1%E9%99%A9%E5%BA%9F%E7%89%A9&depth=1&limit=70"] * 8))
    ok = sum(1 for s, _ in res if s == 200)
    print("  第 %d 轮：%d/8 个 200　总 %.2fs　最慢单个 %.3fs"
          % (rd + 1, ok, time.time() - t0, max(d for _, d in res)))
