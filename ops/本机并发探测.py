#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器本机跑并发，判定 3 秒卡顿是"服务端慢"还是"网络丢包"。

判据：
  · 本机 127.0.0.1 并发 8×/kg/stats 跑 20 轮，如果一次都不卡 →
    问题在网络上（跨机 TCP 重传超时恰好 3s），不是服务端的锅。
  · 如果本机也卡 3 秒 → 确实是服务端把事件循环堵住了，得改代码。
"""
from __future__ import annotations

import concurrent.futures as cf
import time
import urllib.request

BASE = "http://127.0.0.1:8011"


def hit(path: str) -> tuple[int, float]:
    t0 = time.time()
    try:
        with urllib.request.urlopen(BASE + path, timeout=30) as r:
            r.read()
            return r.status, time.time() - t0
    except Exception:                                             # noqa: BLE001
        return -1, time.time() - t0


print("=" * 92)
print("本机 127.0.0.1：并发 8 次 /kg/stats，跑 20 轮")
print("=" * 92)
worst = 0.0
bad = 0
for rd in range(20):
    t0 = time.time()
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        res = list(ex.map(hit, ["/kg/stats"] * 8))
    ok = sum(1 for s, _ in res if s == 200)
    mx = max(d for _, d in res)
    worst = max(worst, mx)
    flag = ""
    if ok != 8 or mx > 0.5:
        bad += 1
        flag = "   <-- 异常"
    print("  第 %2d 轮：%d/8 个 200　总 %.3fs　最慢单个 %.3fs%s"
          % (rd + 1, ok, time.time() - t0, mx, flag))

print()
print("  异常轮数：%d / 20　全局最慢单个：%.3fs" % (bad, worst))
print("  结论：" + ("本机也卡 → 服务端问题" if bad else "本机不卡 → 网络问题（跨机 TCP 重传）"))
