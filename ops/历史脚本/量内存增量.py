#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量"每个任务泄漏多少内存"。

代码层面已经确认 `_JOBS` / `_SESS` 从不清理（gen_routes.py L42/L77、audit_routes.py L33），
但"从不清理"要变成"泄漏"必须有量级证据：3.3GB 的 RSS 里可能大部分是启动基线
（知识图谱 + 审核引擎）。所以这里做**差值测量**：

  基线 RSS → 跑 N 个编制任务 → 再测 RSS → 除以 N = 单任务增量

注意：这是差值，不是绝对值归属。它只能说明"跑任务会让 RSS 单调上涨"，
不能单独证明上涨的全部来自 _JOBS。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://10.201.31.10:8011"
PID_FILE = "/tmp/_leak_pid"


def rss_kb() -> int:
    """读本机服务进程的 RSS。脚本在 Windows 上跑，所以通过 HTTP 拿不到 —— 由调用方传参。"""
    raise NotImplementedError


def post(path: str, body: object) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


def get(path: str) -> dict:
    with urllib.request.urlopen(BASE + path, timeout=300) as r:
        return json.loads(r.read().decode())


def run_one_gen(i: int) -> tuple[str, float]:
    """跑一次报告编制，返回 (job_id, 耗时)。用不同的描述避免命中叙述缓存。"""
    txt = ("这是第 %d 号测试项目。建设地点在江苏省南京市江宁区，"
           "项目为建设一条年产 %d 万吨的水泥熟料生产线，总投资 %d 万元，"
           "占地面积约 %d 平方米。周边 500 米范围内有居民区。" % (i, i + 1, 5000 * i, 1000 * i))
    r = post("/gen/api/chat/start", {"text": txt})
    sid = r["session"]
    # 直接生成，跳过问答
    r = post("/gen/api/chat/generate", {"session": sid, "model": True})
    job = r["job"]
    t0 = time.time()
    while time.time() - t0 < 180:
        j = get("/gen/api/job/" + job)
        if j.get("job", {}).get("status") in ("done", "failed", "rejected"):
            return job, time.time() - t0
        time.sleep(1.5)
    return job, -1.0


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    print("=" * 90)
    print("单任务内存增量测量：连跑 %d 个编制任务" % n)
    print("=" * 90)
    print("请先记下基线 RSS（本脚本只负责跑任务并报耗时）。")
    print()
    for i in range(n):
        job, secs = run_one_gen(i)
        print("  第 %d 个任务  job=%s  %.1fs" % (i + 1, job, secs))
    print()
    print("跑完了。现在再测一次 RSS 与基线做差。")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    sys.exit(main())
