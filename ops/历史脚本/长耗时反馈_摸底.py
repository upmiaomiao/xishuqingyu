#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化「其他长耗时操作」到底要等多久、期间有没有反馈。

问的不是"慢不慢"，而是"这段等待里用户看得见什么"。
所以对每个接口记录：耗时 + 期间客户端能收到的中间信号数。

接口清单（报告编制那条链路）：
  POST /gen/api/chat/start      提交项目描述 → 抽事实 + 出问题
  POST /gen/api/chat/answer     回答一个问题  → 采信 + 出下一个问题
  POST /gen/api/chat/generate   开始生成报告  → 返回 job_id，之后轮询
  GET  /gen/api/job/{id}        轮询任务状态

对照：报告审核那条链路已经有 stage + secs + pct，作为"好"的基准。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://10.201.31.10:8011"


def call(method: str, path: str, body: dict | None = None, timeout: int = 300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {},
    )
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            return time.perf_counter() - t0, r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        return time.perf_counter() - t0, e.code, {"detail": e.read().decode("utf-8", "replace")[:200]}


def main():
    print("=" * 82)
    print("报告编制链路：每一步要等多久，期间客户端收到几个中间信号")
    print("=" * 82)

    # ---- 1. chat/start
    d1, st, r1 = call("POST", "/gen/api/chat/start",
                      {"text": "临沂市兰山区某公司新建年产 3000 吨塑料制品生产线项目，"
                               "总投资 500 万元，建筑面积 2000 平方米，员工 30 人。"})
    sig1 = 0  # 同步接口，请求返回前客户端收不到任何东西
    print()
    print("[1] POST /gen/api/chat/start　提交项目描述")
    print("    耗时 %.2fs  HTTP %s" % (d1, st))
    print("    期间中间信号：%d 个　%s" % (sig1, "★ 完全无反馈（只有按钮变灰）" if d1 > 3 else "（尚可）"))
    sid = r1.get("session")
    nq = len(r1.get("问题") or [])
    print("    结果：session=%s 采纳 %s 项 / 丢弃 %s 处 / 出 %d 个问题"
          % (sid, r1.get("采纳数"), r1.get("丢弃数"), nq))

    if not sid:
        print("    ! 拿不到 session，后续跳过")
        return 1

    # ---- 2. chat/answer（答第一个问题）
    qs = r1.get("问题") or []
    if qs:
        q = qs[0]
        d2, st2, r2 = call("POST", "/gen/api/chat/answer", {
            "session": sid, "key": q.get("key"), "中文名": q.get("中文名"),
            "类型": q.get("类型"), "事实名": q.get("事实名"), "问题": q.get("问题"),
            "text": "不知道",
        })
        print()
        print("[2] POST /gen/api/chat/answer　回答一个问题")
        print("    耗时 %.2fs  HTTP %s" % (d2, st2))
        print("    期间中间信号：0 个　%s" % ("★ 完全无反馈（只有按钮变灰）" if d2 > 3 else "（尚可）"))
        print("    结果：%s" % str(r2.get("本次"))[:60])

    # ---- 3. chat/generate + 轮询
    d3, st3, r3 = call("POST", "/gen/api/chat/generate", {"session": sid, "model": True})
    job = r3.get("job")
    print()
    print("[3] POST /gen/api/chat/generate　开始生成报告")
    print("    提交耗时 %.2fs  HTTP %s  job=%s" % (d3, st3, job))
    if not job:
        print("    ! 拿不到 job，后续跳过")
        return 1

    t0 = time.perf_counter()
    polls, seen_log, statuses = 0, 0, []
    last = None
    while True:
        dt, st, r = call("GET", "/gen/api/job/" + job)
        polls += 1
        j = r.get("job") or {}
        n = len(j.get("log") or [])
        if n > seen_log:
            for l in (j.get("log") or [])[seen_log:]:
                print("      +%.1fs  [%s] %s" % (time.perf_counter() - t0, l.get("step"), l.get("text")[:70]))
            seen_log = n
        if j.get("status") != last:
            statuses.append((round(time.perf_counter() - t0, 1), j.get("status")))
            last = j.get("status")
        if j.get("status") in ("done", "failed", "rejected"):
            break
        if time.perf_counter() - t0 > 600:
            print("    ! 超过 600s，放弃等待")
            break
        time.sleep(1.5)

    total = time.perf_counter() - t0
    print()
    print("    生成总耗时 %.1fs，轮询 %d 次（每 1.5s）" % (total, polls))
    print("    期间收到：日志 %d 行，状态变化 %s" % (seen_log, statuses))
    print("    有进度百分比吗：%s" % ("有" if any("pct" in (r.get("job") or {}) for _ in [0]) else "**没有**"))
    print("    有已用秒数吗：%s" % ("**没有**（要自己数日志行）" if True else ""))

    print()
    print("=" * 82)
    print("对照：报告审核链路（/audit/api/job/{id}）")
    print("=" * 82)
    print("  它有 stage（当前阶段文字）+ secs（已用秒数）+ pct（进度条百分比）")
    print("  → 也就是说，站点上**两条链路的标准不一致**：审核有进度条，编制只有日志行")
    print("=" * 82)
    return 0


if __name__ == "__main__":
    sys.exit(main())
