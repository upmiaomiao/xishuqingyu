#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务端：通过 HTTP 接口跑一份审核并轮询结果（用法：跑审核.py <报告名> [true|false]）。"""
import json
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011/audit"
name = sys.argv[1]
use_llm = sys.argv[2] if len(sys.argv) > 2 else "true"

req = urllib.request.Request(
    BASE + "/api/run?name=" + urllib.parse.quote(name) + "&use_llm=" + use_llm, data=b"")
j = json.load(urllib.request.urlopen(req, timeout=30))
print("job:", j)
t0 = time.time()
for _ in range(400):
    time.sleep(3)
    s = json.load(urllib.request.urlopen(BASE + "/api/job/" + j["job"], timeout=30))
    print("  [%5.0fs] %s %s%%" % (time.time() - t0, s.get("stage"), s.get("pct")))
    if not s.get("done"):
        continue
    if s.get("error"):
        print("失败：", s["error"])
        print(s.get("trace", ""))
        break
    res = s["result"]
    print("统计:", json.dumps(res["统计"], ensure_ascii=False), " 用时", s.get("secs"), "s")
    for it in res["items"]:
        print("  %-6s %-22s %-7s %s" % (it["AI审核"], it["审核项"], it["环评文件"] or "",
                                        (it["理由"] or "")[:96]))
        for e in it["证据"][:2]:
            print("         证据 P%s %s" % (e["page"], (e["quote"] or "")[:74]))
        for c in it.get("需人工确认", []):
            print("         ! ", c[:88])
    for c in res["冲突"]:
        print("  !! 冲突", c["输入"], "正则=", c["正则"], "模型=", c["模型"])
    break