#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务端自检：判据目录 / 报告清单 / 引擎导入 / 一份报告全流程（不带模型）。"""
import os
import sys
import time

sys.path.insert(0, "/data/eia_audit")
sys.path.insert(0, "/home/test/xishu_qingyu_serve")

print("python", sys.version.split()[0])
try:
    import fitz
    print("pymupdf", fitz.version)
except Exception as exc:
    print("pymupdf 缺失：", exc)

from audit.criteria import DEFAULT_DIR, Criteria          # noqa: E402
from audit.runner import audit_file, cache_dir, list_reports, report_dir  # noqa: E402

print("判据目录:", DEFAULT_DIR, os.path.isdir(DEFAULT_DIR))
C = Criteria()
print("名录条目数:", len(C.catalog), " 风险物质:", len(C.risk.get("substances", [])))
print("报告目录:", report_dir())
names = list_reports()
print("报告 %d 份:" % len(names))
for n in names:
    print("   -", n)

print("\n缓存目录:", cache_dir())
if len(sys.argv) > 1 and sys.argv[1] == "full":
    t0 = time.time()
    r = audit_file(os.path.join(report_dir(), names[-1]), use_llm=False)
    print("单份全流程 %.1fs" % (time.time() - t0), r["统计"])
    for it in r["items"]:
        print("   ", it["AI审核"], it["审核项"], it["环评文件"], it["理由"][:60])
    for c in r["冲突"]:
        print("   !! 冲突", c["输入"], c["正则"], c["模型"])

# ---- 接口自检（人工复核保存 / 导出 / 下载）----
if len(sys.argv) > 1 and sys.argv[1] == "api":
    import json
    import urllib.request

    BASE = "http://127.0.0.1:8011"

    def call(path, data=None):
        req = urllib.request.Request(BASE + path)
        body = None
        if data is not None:
            body = json.dumps(data).encode()
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, body, timeout=180) as resp:
            return resp.status, json.loads(resp.read().decode())

    n0 = names[0]
    # 人工复核/导出都要求该报告**已有审核结果落盘**；挑一份已经跑过的，
    # 避免自检把"还没跑过审核"的 404 当成接口故障（实测踩过）。
    _rd = "/data/eia_audit/_审核结果"
    have = [n for n in names if os.path.isfile(os.path.join(_rd, n.rsplit(".", 1)[0] + ".json"))]
    if not have:
        print("还没有任何报告落盘过审核结果，先跑一份：", n0)
        audit_file(os.path.join(report_dir(), n0), use_llm=False)
        have = [n0]
    n0 = have[0]
    print("接口自检用报告：", n0)
    st, r = call("/audit/api/review/" + urllib.request.quote(n0))
    print("review:", st, "已有复核", len(r.get("items") or {}), "项")
    items = {"环评类别准确性": {"人工修改": "无问题", "备注": "自检写入"}}
    st, r = call("/audit/api/save", {"name": n0, "items": items})
    print("save:", st, r)
    st, r = call("/audit/api/review/" + urllib.request.quote(n0))
    print("review 回读:", st, (r.get("items") or {}).get("环评类别准确性"))
    try:
        call("/audit/api/save", {"name": n0, "items": {"不存在的项": {"人工修改": "无问题"}}})
        print("!! 非法审核项没有被拒绝 —— 接口校验有问题")
    except Exception as exc:
        print("非法审核项被拒绝（预期）:", type(exc).__name__, exc)
    # 导出与下载
    st, r = call("/audit/api/export/" + urllib.request.quote(n0) + "?fmt=csv")
    print("export csv:", st, r)
    f = r.get("file")
    with urllib.request.urlopen(BASE + "/audit/api/download/" + urllib.request.quote(f), timeout=60) as resp:
        head = resp.read(120)
        print("download:", resp.status, resp.headers.get("content-type"), head[:60])
    st, r = call("/audit/api/export/" + urllib.request.quote(n0) + "?fmt=json")
    print("export json:", st, r)