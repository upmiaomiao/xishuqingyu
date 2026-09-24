#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务端：删掉"与新判定不一致"的过期交付件（2026-09-22 [021] 重跑之后）。

用户 2026-09-22 的决定：「删除吧，等待用户导出」。

为什么要按报告挑着删，而不是清空 `导出/`：
  重跑后只有 3 份报告的判定变了（临沂 / 1、环评报告 / 生物质环评），
  另外 3 份（邵武 / 常德 / fde112）的 18 项**一条都没变**，它们的交付件仍然与结果一致 —— 没必要删。

安全两条（都要满足才动手）：
  ① 该文件在备份目录里有**同名同大小**的副本（删错了也能立刻找回）；
  ② 文件名前缀必须是"判定变过的那 3 份报告"。

用法：/home/test/fagui_serve/.venv/bin/python 删过期交付件.py [--apply]
不加 --apply 只报告要删什么。
"""
from __future__ import annotations

import os
import sys

EXPORT = "/data/eia_audit/_审核结果/导出"
BACKUP = "/home/test/_重构归档_20260922/第三批_前/审核结果_重跑前/导出"

# 判定发生变化的 3 份报告（见 _工作记录/重跑对账.json）
CHANGED = (
    "1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书",
    "1、环评报告",
    "生物质环评",
)

apply = "--apply" in sys.argv
todo, kept, blocked = [], [], []

for f in sorted(os.listdir(EXPORT)):
    p = os.path.join(EXPORT, f)
    if not os.path.isfile(p):
        continue
    owner = next((c for c in CHANGED if f.startswith(c)), None)
    if not owner:
        kept.append(f)
        continue
    b = os.path.join(BACKUP, f)
    ok = os.path.exists(b) and os.path.getsize(b) == os.path.getsize(p)
    (todo if ok else blocked).append((f, os.path.getsize(p)))

print("判定变过的 3 份报告 → 交付件过期，待删：%d 个" % len(todo))
for f, n in todo:
    print("   - %-72s %8.1f MB" % (f[:72], n / 1048576))
print("\n判定没变的 3 份报告 → 交付件仍与结果一致，保留：%d 个" % len(kept))
for f in kept:
    print("   · %s" % f[:78])
if blocked:
    print("\n！备份里没有同尺寸副本，**不删**：%d 个" % len(blocked))
    for f, n in blocked:
        print("   ? %s" % f)

if not apply:
    print("\n（未加 --apply，什么都没删）")
    sys.exit(0)

freed = 0
for f, n in todo:
    os.remove(os.path.join(EXPORT, f))
    freed += n
print("\n已删除 %d 个，释放 %.1f MB" % (len(todo), freed / 1048576))
print("回滚：cp -a %s/. %s/" % (BACKUP, EXPORT))
print("重出：在审核页对相应报告点「导出」（或走 /audit/api/export_docx|export_pdf）。")
