#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把服务器代码清单与仓库文件清单做差集：找出"线上有、仓库没有"的文件。

用法：python 差集_线上缺哪些.py <服务器代码清单.txt>
"""
from __future__ import annotations

import io
import os
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "xishuqingyu"))


def repo_files() -> set:
    out = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True,
                         encoding="utf-8").stdout
    return {line.strip() for line in out.splitlines() if line.strip()}


def to_repo_path(rel: str) -> str:
    parts = rel.split("/")
    if len(parts) == 3 and parts[0] == "home" and parts[1] == "test" and parts[2].endswith((".py", ".sh")):
        return "ops/" + parts[2]
    return "server/" + rel


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    server = [l.strip() for l in io.open(sys.argv[1], encoding="utf-8") if l.strip()]
    have = repo_files()
    missing = [s for s in server if to_repo_path(s) not in have]
    extra = sorted(r for r in have
                   if r not in {to_repo_path(s) for s in server}
                   and not r.startswith(("ops/", "server/")) is False)

    print("线上代码 %d 个；仓库 %d 个" % (len(server), len(have)))
    print("\n== 线上有、仓库没有（%d 个）==" % len(missing))
    for s in missing:
        print("   ❌ /%s" % s)
    print("\n== 仓库有、线上文件清单里没有（%d 个，多为仓库自身的 README/.gitignore 或我补写的脚本）=="
          % len(extra))
    for r in extra[:30]:
        print("   · %s" % r)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
