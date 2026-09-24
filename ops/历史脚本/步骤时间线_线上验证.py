#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线上真实 SSE 验证：观察步骤事件到达的时间间隔。

这是这次改动的核心证据 —— 用户抱怨的不是"慢"，是"长时间没有任何反馈"。
所以这里不只检查事件内容，还**记录每个事件到达的时刻**，把间隔打出来：
改之前，照片研判会有一段几十秒的空档（读图 + 整段 JSON 生成）；
改之后，最长间隔应该被压在 1 秒左右（进度节流是 0.8s）。

用法：python 步骤时间线_线上验证.py [--photo]
"""
from __future__ import annotations

import base64
import json
import sys
import time
import urllib.request

BASE = "http://10.201.31.10:8011"

# 一张 8x8 的纯色 PNG（够触发视觉通路，又不至于让上传变慢）
PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAHElEQVQoz2NkYPjPQAxgYiASjCoc"
    "VTiqcNAqBABGtgEBrfjXwQAAAABJRU5ErkJggg=="
)


def stream(payload: dict, label: str) -> list[tuple[float, str, dict]]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream", data=body,
        headers={"Content-Type": "application/json"}, method="POST",
    )
    t0 = time.perf_counter()
    events: list[tuple[float, str, dict]] = []
    ev = ""
    with urllib.request.urlopen(req, timeout=300) as r:
        print("  HTTP %s  %s" % (r.status, r.headers.get("content-type")))
        buf = ""
        for raw in r:
            line = raw.decode("utf-8", "replace")
            buf += line
            if line.strip() == "" and buf.strip():
                name, data = "", ""
                for ln in buf.split("\n"):
                    s = ln.strip()
                    if s.startswith("event:"):
                        name = s[6:].strip()
                    elif s.startswith("data:"):
                        data += s[5:].strip()
                if name:
                    try:
                        payload_obj = json.loads(data)
                    except Exception:
                        payload_obj = {"_raw": data[:80]}
                    events.append((time.perf_counter() - t0, name, payload_obj))
                buf = ""
    return events


def show(events, label):
    print()
    print("  事件时间线（t = 距发请求的秒数，Δ = 与上一事件的间隔）：")
    prev = 0.0
    gaps = []
    for t, name, d in events:
        gap = t - prev
        gaps.append((gap, name))
        prev = t
        if name == "chunk":
            desc = "正文 %d 字" % len(str(d))
        elif name == "status":
            desc = "%-9s %-8s %s%s" % (
                d.get("stage", "?"), d.get("state", ""), d.get("message", ""),
                ("  [%s]" % d.get("detail")) if d.get("detail")
                else ("  已生成 %s 字" % d.get("progress") if d.get("progress") else ""),
            )
        elif name == "vision":
            desc = "识别内容 %d 字" % len(str(d.get("text", "")))
        elif name == "meta":
            desc = "route=%s sources=%d" % (d.get("route"), len(d.get("sources") or []))
        elif name == "done":
            desc = "route=%s latency=%ss" % (d.get("route"), d.get("latency_s"))
        else:
            desc = str(d)[:70]
        flag = "  ⚠️ 长静默" if gap >= 3.0 else ""
        print("    %7.2fs  Δ%6.2fs  %-9s %s%s" % (t, gap, name, desc, flag))
    statuses = [e for e in events if e[1] == "status"]
    print()
    print("  合计 %d 个事件，其中 status %d 个" % (len(events), len(statuses)))
    worst = max(gaps) if gaps else (0, "")
    print("  最大间隔：%.2fs（在 %s 之前）" % worst)
    return worst[0], len(statuses)


def main():
    photo = "--photo" in sys.argv
    print("=" * 78)
    if photo:
        print("照片研判通路（report=photo + 图片）")
        print("=" * 78)
        payload = {"query": "这是现场照片，帮我研判", "image": "data:image/png;base64," + PNG_B64,
                   "report": "photo", "max_tokens": 1200}
    else:
        print("普通 RAG 通路（纯文本）")
        print("=" * 78)
        payload = {"query": "危险废物转移联单的确认期限是多久？", "max_tokens": 600}
    evs = stream(payload, "x")
    worst, n_status = show(evs, "x")

    print()
    print("=" * 78)
    ok = True
    if n_status == 0:
        print("★ 一个 status 事件都没有 —— 用户看不到任何进度")
        ok = False
    else:
        print("√ 有 %d 个 status 事件（用户能持续看到进度）" % n_status)
    if worst >= 8.0:
        print("★ 仍有 %.1fs 的静默 —— 进度上报不够密" % worst)
        ok = False
    else:
        print("√ 最大间隔 %.2fs，没有长时间无反馈" % worst)
    print("=" * 78)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
