#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第二轮归档：工作区 _脚本代码 下其余目录里"仓库还没有的"脚本。

去重口径：**按文件名**（线上/仓库已有同名文件的就跳过），
所以 audit/gen/static 这些与线上代码重复的副本不会被搬进来，只留真正独有的脚本。
分组保留，落在 ops/工作区脚本/<原目录名>/ 下。
"""
from __future__ import annotations

import os
import shutil
import subprocess

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = os.path.join(WS, "xishuqingyu")
SRC = os.path.join(WS, "_脚本代码")
DONE = {"站点全量测试"}          # 第一轮已处理
SKIP_EMPTY = {"_中间产物"}
CODE_EXT = (".py", ".sh", ".js", ".mjs", ".css", ".html", ".json", ".md", ".txt", ".yml", ".yaml")


def repo_basenames() -> set:
    out = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True,
                         text=True, encoding="utf-8").stdout
    return {os.path.basename(l.strip()) for l in out.splitlines() if l.strip()}


def main() -> int:
    have = repo_basenames()
    total_new = 0
    for d in sorted(os.listdir(SRC)):
        src = os.path.join(SRC, d)
        if not os.path.isdir(src) or d in DONE or d in SKIP_EMPTY:
            continue
        copied = 0
        for dp, dns, fns in os.walk(src):
            dns[:] = [x for x in dns if x not in ("__pycache__", ".venv", "node_modules")]
            for f in fns:
                if not f.endswith(CODE_EXT) or f in have:
                    continue
                rel = os.path.relpath(dp, src)
                dst_dir = os.path.join(REPO, "ops", "工作区脚本", d) if rel == "." \
                    else os.path.join(REPO, "ops", "工作区脚本", d, rel)
                os.makedirs(dst_dir, exist_ok=True)
                shutil.copy2(os.path.join(dp, f), os.path.join(dst_dir, f))
                copied += 1
        total_new += copied
        print("  %-16s 新归档 %3d 个" % (d, copied))
    print("\n本轮合计新归档 %d 个文件" % total_new)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
