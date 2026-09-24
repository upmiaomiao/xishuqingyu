#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看响应头：CORS / 缓存 / 内容类型 / 服务端标识。"""
from __future__ import annotations

import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011"
PATHS = ["/", "/health", "/hybrid_search?query=x", "/kg/stats", "/doc?source=x.md",
         "/gen", "/gen/static/gen_ui.js", "/gen/api/outputs", "/audit",
         "/audit/static/audit_ui.css", "/audit/api/reports", "/openapi.json", "/docs"]

for p in PATHS:
    req = urllib.request.Request(BASE + p, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            h = dict(r.headers)
            st = r.status
    except urllib.error.HTTPError as e:
        h, st = dict(e.headers or {}), e.code
    except Exception as e:                                    # noqa: BLE001
        print("%-34s ERR %s" % (p, e))
        continue
    keep = {k: v for k, v in h.items()
            if k.lower() in ("access-control-allow-origin", "access-control-allow-methods",
                             "cache-control", "content-type", "server", "x-powered-by",
                             "content-disposition", "set-cookie")}
    print("%-34s %s  %s" % (p, st, keep))
