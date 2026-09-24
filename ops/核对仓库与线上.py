#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把线上 md5 清单与本仓库逐文件比对 —— 证明"仓库里的代码 == 线上正在跑的代码"。

映射规则（与导出口径一致）：
  线上 home/test/<平铺脚本>.py|.sh      → 仓库 ops/<同名>
  线上 home/test/<目录>/...             → 仓库 server/home/test/<目录>/...
  线上 data/...                         → 仓库 server/data/...
  线上 <其它>/...                        → 仓库 server/<其它>/...

用法：python 核对仓库与线上.py <线上md5.txt>
"""
from __future__ import annotations

import hashlib
import io
import os
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "xishuqingyu"))


def md5(p: str) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def local_path(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 3 and parts[0] == "home" and parts[1] == "test" and parts[2].endswith((".py", ".sh")):
        return os.path.join(REPO, "ops", parts[2])         # 平铺脚本 → ops/
    return os.path.join(REPO, "server", *parts)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rows = []
    for line in io.open(sys.argv[1], encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        digest, rel = line.split(None, 1)
        rows.append((digest, rel.strip()))

    same = diff = miss = 0
    problems = []
    for digest, rel in rows:
        p = local_path(rel)
        if not os.path.isfile(p):
            miss += 1
            problems.append(("缺失", rel))
            continue
        got = md5(p)
        if got == digest:
            same += 1
        else:
            diff += 1
            problems.append(("内容不同", "%s（线上 %s / 仓库 %s）" % (rel, digest[:8], got[:8])))
    print("比对 %d 个文件：一致 %d ／ 不同 %d ／ 仓库缺失 %d" % (len(rows), same, diff, miss))
    for kind, rel in problems[:25]:
        print("   ❌ %s：%s" % (kind, rel))
    if not problems:
        print("   ✅ 仓库快照与线上代码逐字节一致")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
