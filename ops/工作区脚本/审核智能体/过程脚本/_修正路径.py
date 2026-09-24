#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `过程脚本/` 下的一次性勘察/冒烟脚本改成"位置无关"。

背景：这些脚本原来在 `审核智能体/` 顶层，写的是 `HERE`（自身目录）= 引擎包所在目录。
移进 `过程脚本/` 后，`HERE` 变成了子目录，`import audit` 与 `_cache` 都会找错地方。
这里统一改成：BASE = 上级目录（审核智能体/），sys.path 与缓存都指向 BASE。

只做这一件事，改完打印每个文件的前后差异行，便于人工核对。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 过程脚本/
BASE = os.path.dirname(HERE)                               # 审核智能体/

OLD_HEAD = "HERE = os.path.dirname(os.path.abspath(__file__))\nsys.path.insert(0, HERE)\n"
NEW_HEAD = ("HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（过程脚本/）\n"
            "BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这一层）\n"
            "sys.path.insert(0, BASE)\n")


def main():
    changed = []
    for fn in sorted(os.listdir(HERE)):
        if not fn.endswith(".py") or fn == os.path.basename(__file__):
            continue
        p = os.path.join(HERE, fn)
        src = open(p, encoding="utf-8").read()
        new = src
        if OLD_HEAD in new:
            new = new.replace(OLD_HEAD, NEW_HEAD, 1)
        new = re.sub(r'os\.path\.join\(HERE, "_cache"\)', 'os.path.join(BASE, "_cache")', new)
        if new != src:
            open(p, "w", encoding="utf-8").write(new)
            changed.append(fn)
    print(f"已修正 {len(changed)} 个：")
    for fn in changed:
        print("   -", fn)
    # 复核：确认没有残留的 HERE 缓存路径
    bad = []
    for fn in sorted(os.listdir(HERE)):
        if fn.endswith(".py") and fn != os.path.basename(__file__):
            s = open(os.path.join(HERE, fn), encoding="utf-8").read()
            if 'os.path.join(HERE, "_cache")' in s or "sys.path.insert(0, HERE)" in s:
                bad.append(fn)
    print("残留未修正：", bad or "无")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())