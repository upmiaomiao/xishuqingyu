#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐条复现"失败"的用例，判定到底是站点的问题还是检查器写错了。"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def probe(label, method, path, data=None, headers=None, timeout=60):
    url = BASE + path
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    h = dict(headers or {})
    if body:
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            st, hd, b = resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as e:
        st, hd, b = e.code, dict(e.headers or {}), e.read()
    except Exception as e:                                     # noqa: BLE001
        print("%-52s EXC %s: %s" % (label, type(e).__name__, e))
        return
    print("%-52s HTTP %s" % (label, st))
    print("      headers: %s" % {k: v for k, v in hd.items()
                                 if k.lower() in ("content-type", "cache-control",
                                                  "content-disposition",
                                                  "access-control-allow-origin")})
    print("      body: %s" % b.decode("utf-8", "replace")[:300].replace("\n", " "))


print("=" * 78)
print("A. 头部键大小写（怀疑检查器用 hd.get('Content-Type') 而 uvicorn 给小写）")
probe("GET /", "GET", "/")
probe("GET /gen/static/gen_ui.js", "GET", "/gen/static/gen_ui.js")

print("\n" + "=" * 78)
print("B. /kg/stats 到底返回什么（怀疑检查器误判）")
probe("GET /kg/stats", "GET", "/kg/stats")

print("\n" + "=" * 78)
print("C. POST /hybrid_search 空体（期望 400）")
probe("POST /hybrid_search {}", "POST", "/hybrid_search", data={})

print("\n" + "=" * 78)
print("D. /doc 不存在（中文未编码 → 怀疑是 urllib 报错不是站点 404）")
probe("GET /doc?source=绝对不存在.md (未编码)", "GET", "/doc?source=绝对不存在的文件.md")
probe("GET /doc?source=<已编码>", "GET", "/doc?source=" + urllib.parse.quote("绝对不存在的文件.md"))
probe("GET /doc?source=x.md", "GET", "/doc?source=x.md")

print("\n" + "=" * 78)
print("E. 审核侧 %2f 穿越与不存在文件（中文未编码）")
probe("GET /audit/api/review/..%2fx", "GET", "/audit/api/review/..%2fx")
probe("GET /audit/api/review/%2e%2e%2fx", "GET", "/audit/api/review/%2e%2e%2fx")
probe("GET /audit/api/download/..%2fx", "GET", "/audit/api/download/..%2fx")
probe("GET /audit/api/download/没有.csv (未编码)", "GET", "/audit/api/download/没有.csv")
probe("GET /audit/api/download/<已编码>", "GET", "/audit/api/download/" + urllib.parse.quote("没有.csv"))
probe("GET /audit/api/export/绝对没有.pdf (未编码)", "GET", "/audit/api/export/绝对没有这份报告.pdf")
probe("GET /audit/api/export/<已编码>", "GET",
      "/audit/api/export/" + urllib.parse.quote("绝对没有这份报告.pdf"))

print("\n" + "=" * 78)
print("F. CORS：带 Origin 时是否放开 *（不带 Origin 不会回 CORS 头，属正常）")
probe("GET /health 带 Origin", "GET", "/health", headers={"Origin": "http://evil.example"})
probe("POST /hybrid_search 预检 OPTIONS", "OPTIONS", "/hybrid_search",
      headers={"Origin": "http://evil.example",
               "Access-Control-Request-Method": "POST",
               "Access-Control-Request-Headers": "content-type"})

print("\n" + "=" * 78)
print("G. 报告清单到底几份（8 个 PDF 里应有 1 个重复件被去重）")
probe("GET /audit/api/reports", "GET", "/audit/api/reports")
