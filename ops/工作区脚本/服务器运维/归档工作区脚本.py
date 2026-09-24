#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把工作区里"只在本地、没进仓库"的脚本归档进仓库。

分两类放，避免和线上代码混在一起：
  tests/审核智能体/  ← _脚本代码\\审核智能体\\单测\\*.py（判据层/十八项/审核界面/废气清单/标准现行性/防编造）
  tests/报告生成/    ← _脚本代码\\报告生成\\单测\\*.py
  ops/历史脚本/      ← _脚本代码\\站点全量测试\\*（历次勘察/修复/验收的一次性脚本）

同名文件若仓库 ops/ 里已有（线上就是那份），不重复放。
"""
from __future__ import annotations

import os
import shutil
import subprocess

WS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
REPO = os.path.join(WS, "xishuqingyu")
SRC = os.path.join(WS, "_脚本代码")

JOBS = [
    (os.path.join(SRC, "审核智能体", "单测"), "tests/审核智能体"),
    (os.path.join(SRC, "报告生成", "单测"), "tests/报告生成"),
    (os.path.join(SRC, "站点全量测试"), "ops/历史脚本"),
]


def repo_basenames() -> set:
    out = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True,
                         text=True, encoding="utf-8").stdout
    return {os.path.basename(l.strip()) for l in out.splitlines() if l.strip()}


def main() -> int:
    have = repo_basenames()
    report = []
    for src, dst_rel in JOBS:
        if not os.path.isdir(src):
            report.append("  ⚠️ 源目录不存在：%s" % src)
            continue
        dst = os.path.join(REPO, dst_rel)
        os.makedirs(dst, exist_ok=True)
        copied = skipped = 0
        for f in sorted(os.listdir(src)):
            p = os.path.join(src, f)
            if not os.path.isfile(p):
                continue
            # 线上已有同名脚本的，不重复搬（站点全量测试 这类历史堆里重复很多）
            if dst_rel.startswith("ops/历史脚本") and f in have:
                skipped += 1
                continue
            shutil.copy2(p, os.path.join(dst, f))
            copied += 1
        report.append("  ✅ %-28s → %-24s 复制 %d 个%s"
                      % (os.path.basename(os.path.dirname(src)) + "/" + os.path.basename(src),
                         dst_rel, copied, ("（跳过线上已有同名 %d 个）" % skipped) if skipped else ""))
    print("\n".join(report))

    print("\n== 工作区 _脚本代码 下还有哪些目录（供决定要不要也归档）==")
    for d in sorted(os.listdir(SRC)):
        p = os.path.join(SRC, d)
        if os.path.isdir(p):
            n = sum(len(fs) for _, _, fs in os.walk(p))
            print("   %-24s %4d 个文件" % (d, n))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
