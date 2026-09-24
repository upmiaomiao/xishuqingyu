#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务端只读：重跑后，审核页读回来的结果是不是新的那份（页面走 loadExistingResult 读磁盘 JSON）。

为什么单查这一步：结果 JSON 是**被重跑覆盖**的，如果页面走的是内存缓存或另一份副本，
那用户看到的还是旧结论 —— 那就是"文件改了、界面没改"的假交付。
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011/audit"
NAME = "1、环评报告.pdf"

print("① 报告列表接口（/api/reports）")
try:
    lst = json.load(urllib.request.urlopen(BASE + "/api/reports", timeout=30))
    items = lst if isinstance(lst, list) else (lst.get("files") or lst.get("items") or [])
    hit = [x for x in items if NAME[:12] in json.dumps(x, ensure_ascii=False)]
    print("   报告数 %d，命中 %d" % (len(items), len(hit)))
except Exception as exc:                                            # noqa: BLE001
    print("   列表接口：%s" % exc)

print("\n② 结果接口 /api/result/{name} 返回的判定（应含「环境风险专项评价设置 = 存在疑似问题」）")
try:
    r = json.load(urllib.request.urlopen(
        BASE + "/api/result/" + urllib.parse.quote(NAME), timeout=60))
    res = r.get("result") or r
    st = res.get("统计") or {}
    print("   统计：%s" % json.dumps(st, ensure_ascii=False))
    for it in res.get("items") or []:
        if it.get("审核项") == "环境风险专项评价设置":
            print("   环境风险专项评价设置 → %s" % it.get("AI审核"))
            print("   理由：%s" % str(it.get("理由"))[:110])
except Exception as exc:                                            # noqa: BLE001
    print("   结果接口：%s" % exc)

print("\n③ 导出件是不是旧的（时间戳对照）")
import os                                                           # noqa: E402
import time                                                         # noqa: E402
d = "/data/eia_audit/_审核结果"
for sub in ("导出", ""):
    p = os.path.join(d, sub) if sub else d
    for f in sorted(os.listdir(p))[:4]:
        fp = os.path.join(p, f)
        if os.path.isfile(fp) and f.endswith(".json"):
            print("   %-46s %s" % ((sub + "/" if sub else "") + f[:44],
                                   time.strftime("%m-%d %H:%M", time.localtime(os.path.getmtime(fp)))))
