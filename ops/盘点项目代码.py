#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""盘点服务器上"属于本项目的前后端代码"——列出目录树、代码文件数与体积，
把 venv/__pycache__/索引/数据 排除掉单独报，便于决定 git 里放什么。"""
from __future__ import annotations

import os

ROOTS = [
    "/home/test/xishu_qingyu_serve",     # 8011 站点（前端 + xishu_pipeline）
    "/home/test/fagui_serve",            # 法规问答服务（另一套 venv/服务）
    "/data/eia_audit",                   # 审核引擎
    "/data/eia_report_gen",              # 报告生成引擎
    "/data/fagui_rag",                   # 法规 RAG（语料/索引/脚本）
]
CODE_EXT = (".py", ".js", ".css", ".html", ".json", ".sh", ".md", ".txt", ".yml", ".yaml",
            ".vue", ".ts", ".tsx", ".jsx", ".jinja", ".j2", ".toml", ".cfg", ".ini")
SKIP_DIR = ("__pycache__", ".venv", "venv", "node_modules", ".git", ".mypy_cache",
            ".pytest_cache", "index", "index_v2", "index.bak", "okf_bundles")


def walk(root: str):
    """→ (代码文件列表, 跳过的大目录列表, 其它文件数)"""
    code, skips, other = [], [], 0
    for dp, dns, fns in os.walk(root, topdown=True):
        keep = []
        for d in dns:
            full = os.path.join(dp, d)
            if any(d == s or d.startswith("index.bak") or d.startswith("index_v") for s in SKIP_DIR):
                try:
                    sz = sum(os.path.getsize(os.path.join(dp2, f))
                             for dp2, _, fs in os.walk(full) for f in fs)
                except OSError:
                    sz = 0
                skips.append((os.path.relpath(full, root), sz))
            else:
                keep.append(d)
        dns[:] = keep
        for f in fns:
            full = os.path.join(dp, f)
            if f.endswith(CODE_EXT):
                try:
                    code.append((os.path.relpath(full, root), os.path.getsize(full)))
                except OSError:
                    pass
            else:
                other += 1
    return code, skips, other


for root in ROOTS:
    print("=" * 92)
    if not os.path.isdir(root):
        print("%s  → 不存在" % root)
        continue
    code, skips, other = walk(root)
    tot = sum(s for _, s in code)
    print("%s  → 代码文件 %d 个 / %.2f MB；其它文件 %d 个" % (root, len(code), tot / 1e6, other))
    print("   顶层：%s" % sorted(os.listdir(root))[:18])
    print("   .git 存在？%s" % os.path.isdir(os.path.join(root, ".git")))
    by = {}
    for rel, s in code:
        top = rel.split(os.sep)[0] if os.sep in rel else "(根目录文件)"
        b = by.setdefault(top, [0, 0])
        b[0] += 1
        b[1] += s
    for k in sorted(by, key=lambda x: -by[x][1])[:12]:
        print("     %-34s %4d 个  %8.2f MB" % (k, by[k][0], by[k][1] / 1e6))
    for rel, sz in sorted(skips, key=lambda x: -x[1])[:6]:
        print("     [排除] %-28s %.1f MB" % (rel, sz / 1e6))

print("=" * 92)
print("== /home/test 下的散装脚本（*.py / *.sh，取前 25 个）==")
loose = sorted(f for f in os.listdir("/home/test")
               if f.endswith((".py", ".sh")) and os.path.isfile(os.path.join("/home/test", f)))
print("   共 %d 个：%s" % (len(loose), loose[:25]))
