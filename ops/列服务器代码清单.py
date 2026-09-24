#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""列出服务器上"属于项目的所有代码文件"（排除 venv/缓存/索引/语料/备份/结果），
输出相对路径清单，供与 git 仓库做差集 —— 用来兜住"点名单导出"漏掉的文件。"""
from __future__ import annotations

import os

ROOTS = ["/home/test/xishu_qingyu_serve", "/home/test/fagui_serve",
         "/data/eia_audit", "/data/eia_report_gen", "/data/fagui_rag"]
CODE_EXT = (".py", ".sh", ".js", ".css", ".html", ".json", ".md", ".txt", ".yml", ".yaml",
            ".ts", ".vue", ".svg", ".doc", ".docx", ".pdf", ".csv")
# 目录名命中即整棵跳过
SKIP_DIR = ("__pycache__", ".venv", ".venv_tools", "venv", "node_modules", ".git",
            "index", "okf_bundles", "okf_bundles_stage", "okf_bundles_eia_sample",
            "eia_reports_raw", "guides_pdf", "_staging", "_cache", "_cache_narr",
            "_cache_intake", "_审核结果", "_生成结果", "_导出代码", "_backup_标题修正_20260921")
OUT = "/home/test/_导出代码/服务器代码清单.txt"


def skip_dir(name: str) -> bool:
    if name in SKIP_DIR:
        return True
    return (name.startswith("index.bak") or name.startswith("okf_bundles.bak")
            or name.startswith("_backup_") or name.startswith("frontend.bak")
            or name.startswith("xishu_pipeline.bak") or name.startswith("_raw")
            or name.startswith("_eia_audit_残留"))


def skip_file(name: str) -> bool:
    return (name.startswith(".") and name not in (".env.example",)
            or name.endswith((".pyc", ".log", ".pid", ".tar.gz", ".zip", ".bak"))
            or ".bak_before_" in name or ".bak_p" in name)


def main() -> int:
    rows = []
    for root in ROOTS:
        if not os.path.isdir(root):
            continue
        for dp, dns, fns in os.walk(root, topdown=True):
            dns[:] = [d for d in dns if not skip_dir(d)]
            for f in fns:
                if f.endswith(CODE_EXT) and not skip_file(f):
                    rows.append(os.path.relpath(os.path.join(dp, f), "/"))
    # /home/test 顶层散装脚本
    for f in sorted(os.listdir("/home/test")):
        p = "/home/test/" + f
        if os.path.isfile(p) and f.endswith((".py", ".sh")) and not skip_file(f):
            rows.append("home/test/" + f)

    # 站点目录下的顶层文件（上一版导出就是漏了这里）
    site = "/home/test/xishu_qingyu_serve"
    for f in sorted(os.listdir(site)):
        p = os.path.join(site, f)
        if os.path.isfile(p) and f.endswith(CODE_EXT) and not skip_file(f):
            rows.append("home/test/xishu_qingyu_serve/" + f)

    rows = sorted(set(rows))
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(rows) + "\n")
    print("服务器代码文件 %d 个 → %s" % (len(rows), OUT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
