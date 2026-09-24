#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报告编制反馈改动 · 线上验证。

检查三件事：
  1. /gen/api/job/{id} 现在带回 stage / pct / secs（原先只有 log）
  2. pct 随阶段推进（不是一直 4）
  3. 前端拿到的 gen_ui.js / gen_ui.css 里确实有等待气泡与进度条
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

BASE = "http://10.201.31.10:8011"
ok_all = True


def call(method, path, body=None, timeout=300):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
        return r.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)


def ck(label, cond, extra=""):
    global ok_all
    print(("  √ " if cond else "  ✗ ") + label + (("　" + str(extra)) if extra else ""))
    if not cond:
        ok_all = False


print("=" * 84)
print("① 静态资源：前端确实拿到了新的等待气泡与进度条")
print("=" * 84)
st, js = call("GET", "/gen/static/gen_ui.js")
ck("gen_ui.js 可访问", st == 200 and isinstance(js, str), "HTTP %s" % st)
if isinstance(js, str):
    ck("有 waitBubble 等待气泡", "function waitBubble" in js)
    ck("等待气泡有走动秒表", "ge-secs" in js and "setInterval" in js)
    ck("有 setProgress 进度条", "function setProgress" in js)
    ck("轮询里调用了 setProgress", "setProgress(j.stage, j.pct, j.secs, j.step, j.steps)" in js)
    ck("进度条显示「第 N/M 步」（百分比只表示走完几步，不谎报剩余时间）",
       '"（第 " + step + "/" + steps + " 步）"' in js)
    ck("补充描述分支也有等待气泡", "waitBubble" in js and js.count("waitBubble(") >= 3,
        "%d 处调用" % js.count("waitBubble("))

st, css = call("GET", "/gen/static/gen_ui.css")
ck("gen_ui.css 可访问", st == 200 and isinstance(css, str), "HTTP %s" % st)
if isinstance(css, str):
    ck("有 .ge-prog 进度条样式", ".ge-prog" in css)
    ck("有 .ge-msg.ge-wait 等待气泡样式", ".ge-msg.ge-wait" in css)
    ck("有减弱动效的降级", "prefers-reduced-motion" in css)

print()
print("=" * 84)
print("② 任务状态：现在带回 stage / pct / secs，且 pct 随阶段推进")
print("=" * 84)
st, r = call("POST", "/gen/api/chat/start",
             {"text": "临沂市兰山区某公司新建年产 3000 吨塑料制品生产线项目，"
                      "总投资 500 万元，建筑面积 2000 平方米，员工 30 人。"})
sid = r.get("session")
ck("建了会话", bool(sid), sid)

# 默认走 fresh。原因：描述文本与上次相同 → 叙述命中缓存 → 整个任务 0.4s 就完了，
# 1.5s 的轮询只采得到一次样，「pct 随阶段推进」这条根本无从观察（会假失败）。
# fresh 会真的调模型（约 4~7s），采样才够。要跑缓存路径用 --cached。
st, r = call("POST", "/gen/api/chat/generate",
             {"session": sid, "model": True, "fresh": ("--cached" not in sys.argv)})
job = r.get("job")
ck("建了生成任务", bool(job), job)

seen_pct, seen_stage, rows = [], [], []
t0 = time.perf_counter()
while time.perf_counter() - t0 < 300:
    st, r = call("GET", "/gen/api/job/" + job)
    j = r.get("job") or {}
    if j.get("pct") not in seen_pct:
        seen_pct.append(j.get("pct"))
    if j.get("stage") and j.get("stage") not in seen_stage:
        seen_stage.append(j.get("stage"))
    rows.append((round(j.get("secs") or 0, 1), j.get("stage"), j.get("pct")))
    if j.get("status") in ("done", "failed", "rejected"):
        final = j
        break
    time.sleep(1.0)
else:
    final = {}

print("    采样（秒数 / 阶段 / 百分比）：")
for s, stg, p in rows[:14]:
    print("      %6.1fs  %-8s %s%%" % (s, stg or "-", p))
if len(rows) > 14:
    print("      …共 %d 次采样" % len(rows))

ck("job 里有 secs 字段", any(r[0] for r in rows), "最大 %.1fs" % max(r[0] for r in rows))
ck("job 里有 stage 字段", bool(seen_stage), " → ".join(seen_stage))
ck("job 里有 pct 字段", bool(seen_pct), str(seen_pct))
# 采样太少就不判"推进"：任务跑得比轮询间隔快时只有一次采样，那是**采样不足**，
# 不是机制坏了。第一版无条件断言 len(seen_pct) > 1，遇到命中缓存的 0.4s 快跑就假失败。
if len(rows) >= 2:
    ck("pct 随阶段推进（不止一个值）", len(seen_pct) > 1, str(seen_pct))
else:
    print("  － 只采到 %d 次样（任务比轮询间隔快），跳过「pct 推进」检查" % len(rows))
ck("secs 单调不减", all(rows[i][0] <= rows[i + 1][0] + 0.01 for i in range(len(rows) - 1)))
ck("结束时 pct = 100", final.get("pct") == 100, final.get("pct"))
ck("任务成功完成", final.get("status") == "done", final.get("status"))

print()
print("=" * 84)
print("③ 对照：报告审核链路（本来就是好的，不能被我改坏）")
print("=" * 84)
st, a = call("GET", "/audit/api/reports")
ck("审核 /reports 仍可用", st == 200 and isinstance(a, dict), "HTTP %s" % st)

print()
print("=" * 84)
print("结论：" + ("全部通过" if ok_all else "有失败项"))
print("=" * 84)
sys.exit(0 if ok_all else 1)
