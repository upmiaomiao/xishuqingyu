#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查两件事：
  1. _生成结果 里最新那份 docx 是谁写的、什么时候写的
  2. /audit/api/run 与 /audit/api/job 的真实返回结构（我上一版轮询键名猜错了）
"""
from __future__ import annotations

import glob
import json
import os
import time
import urllib.parse
import urllib.request

OUT = "/data/eia_report_gen/_生成结果"
BASE = "http://127.0.0.1:8011"


def get(path, timeout=300):
    r = urllib.request.Request(BASE + path, method="GET")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def post(path, timeout=900):
    r = urllib.request.Request(BASE + path, data=b"", headers={}, method="POST")
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


print("=== 1. _生成结果 最新 6 份 docx ===")
files = [(os.path.getmtime(p), p) for p in glob.glob(os.path.join(OUT, "*.docx"))]
files.sort(reverse=True)
for mt, p in files[:6]:
    print("  %s  %8d  %s" % (time.strftime("%m-%d %H:%M:%S", time.localtime(mt)),
                             os.path.getsize(p), os.path.basename(p)))
print("  顶层 .docx 共 %d 份" % len(files))
print("  现在时间：%s" % time.strftime("%m-%d %H:%M:%S"))

print()
print("=== 2. 审核接口真实返回结构 ===")
reps = get("/audit/api/reports")
print("  /audit/api/reports 键：%s" % sorted(reps.keys()))
name = reps["reports"][0]["name"]
print("  取第一份：%s" % name)

run = post("/audit/api/run?name=%s&use_llm=true" % urllib.parse.quote(name))
print("  /audit/api/run 返回键：%s" % sorted(run.keys()))
print("  /audit/api/run 全文：%s" % json.dumps(run, ensure_ascii=False)[:200])

job = run.get("job") or run.get("id") or run.get("job_id")
print("  取到 job=%r" % job)

for i in range(60):
    j = get("/audit/api/job/%s" % job)
    if i == 0:
        print("  /audit/api/job 返回键：%s" % sorted(j.keys()))
    st = j.get("status")
    if st in ("done", "failed", "error"):
        print("  第 %d 次轮询：status=%s" % (i + 1, st))
        print("  完整键与关键值：")
        for k in sorted(j.keys()):
            v = j[k]
            s = json.dumps(v, ensure_ascii=False)
            print("    %-14s %s" % (k, s[:110]))
        break
    time.sleep(1)
else:
    print("  60 次轮询仍未到终态，最后一次：%s" % json.dumps(j, ensure_ascii=False)[:200])
