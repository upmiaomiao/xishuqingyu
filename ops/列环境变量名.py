#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出服务用到的环境变量**名字**（不打印任何值），用于生成 .env.example。

两路收集：
  ① 线上 .env 里的键名（值一律不读出来）；
  ② 代码里 os.environ / os.getenv 出现的名字（含 .get 默认值提示）。
"""
from __future__ import annotations

import os
import re

TARGETS = [
    "/home/test/xishu_qingyu_serve",
    "/home/test/fagui_serve",
    "/data/eia_audit/audit",
    "/data/eia_report_gen/gen",
    "/data/fagui_rag",
]
PAT = re.compile(r"""(?:os\.environ(?:\.get)?\s*[\[(]\s*["']([A-Z0-9_]{3,})["']"""
                 r"""|getenv\s*\(\s*["']([A-Z0-9_]{3,})["'])""")

print("==== ① .env 里的键名（不含值）====")
for env in ("/home/test/xishu_qingyu_serve/.env", "/home/test/fagui_serve/.env",
            "/data/eia_audit/.env", "/data/eia_report_gen/.env"):
    if not os.path.isfile(env):
        continue
    print("  %s：" % env)
    with open(env, encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            print("     %s" % line.split("=", 1)[0].strip())

print("\n==== ② 代码里读到的环境变量名 ====")
found = {}
for root in TARGETS:
    if not os.path.isdir(root):
        continue
    for dp, dns, fns in os.walk(root):
        dns[:] = [d for d in dns if d not in ("__pycache__", ".venv", ".venv_tools",
                                              "node_modules", "index", "okf_bundles")]
        for f in fns:
            if not f.endswith((".py", ".sh")):
                continue
            p = os.path.join(dp, f)
            try:
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for m in PAT.finditer(txt):
                name = m.group(1) or m.group(2)
                found.setdefault(name, set()).add(os.path.relpath(p, root))
for name in sorted(found):
    where = sorted(found[name])
    print("  %-28s 出现在 %d 个文件（如 %s）" % (name, len(where), where[0]))
