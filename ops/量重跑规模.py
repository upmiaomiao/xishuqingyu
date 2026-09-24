#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：为 [021]「已审核结果重跑」量一下规模与耗时（不改任何东西）。

为什么要先量：重跑会**覆盖结果 JSON**（人工复核件另存在 _审核结果/人工/，不会丢），
而且在跑之前得说清"要跑几份、大概多久"。这里从已有结果里读出规模与耗时字段，
不启动任何审核。
"""
from __future__ import annotations

import glob
import json
import os

D = "/data/eia_audit/_审核结果"
files = sorted(glob.glob(os.path.join(D, "*.json")), key=os.path.getmtime)
print("可重跑的结果 JSON：%d 份" % len(files))
print("人工复核副本（不受重跑影响）：%d 份" % len(glob.glob(os.path.join(D, "人工", "*.json"))))
print("导出件：%d 份" % len(glob.glob(os.path.join(D, "导出", "*.json"))))

if files:
    f = files[-1]
    d = json.load(open(f, encoding="utf-8"))
    print("\n样本：%s" % os.path.basename(f))
    print("顶层字段：%s" % list(d.keys())[:16])
    for k in ("耗时", "耗时s", "duration", "用时", "generated_at", "时间", "生成时间"):
        if k in d:
            print("  %s = %s" % (k, d[k]))
    for k in ("结论", "items", "问题", "页"):
        v = d.get(k)
        if isinstance(v, list):
            print("  %s：%d 条" % (k, len(v)))
    # 页数/块数之类的规模指标
    for k in ("页数", "总页数", "chunks", "块数"):
        if k in d:
            print("  %s = %s" % (k, d[k]))

print("\n入口脚本（人工触发用）：")
for p in ("/data/eia_audit/run_audit.py", "/data/eia_audit/run_via_http.py"):
    print("  %s %s" % (p, "存在" if os.path.exists(p) else "不存在"))
print("\n最老/最新结果的修改时间：")
for f in (files[:1] + files[-1:]):
    import time
    print("  %s  %s" % (os.path.basename(f)[:44],
                        time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(f)))))
