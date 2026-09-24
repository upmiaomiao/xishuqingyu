#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""删掉尾部两行孤儿（上一步正则截断留下的），并校验 CSS 括号配平。

孤儿（文件最后两行）：
    .ge-chat-body { max-height: none; }
    }
"""
from __future__ import annotations

import io

P = r"_中间产物/线上源码/gen_ui.css"
src = io.open(P, encoding="utf-8").read()

lines = src.rstrip("\n").split("\n")
print("删前最后 3 行：")
for ln in lines[-3:]:
    print("  |%s" % ln)

assert lines[-1].strip() == "}", "最后一行不是 }"
assert "ge-chat-body" in lines[-2] and "max-height: none" in lines[-2], "倒数第二行不是孤儿"

lines = lines[:-2]
src = "\n".join(lines) + "\n"
io.open(P, "w", encoding="utf-8", newline="\n").write(src)

print()
print("=== 删后尾部 8 行 ===")
out = src.split("\n")
for i, ln in enumerate(out[-8:], start=len(out) - 7):
    print("%3d| %s" % (i, ln))

print()
print("=== CSS 括号配平 ===")
depth = 0
bad = []
for i, ln in enumerate(out, 1):
    for ch in ln:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                bad.append(i)
print("  最终 depth = %d（应为 0）" % depth)
print("  提前闭合行 = %s（应为空）" % bad)

print()
print("=== 残留检查（应全为 0）===")
for k in ["ge-foot", "max-height: 720px", "position: sticky", "max-height: 46vh", "max-height: none", "100vh - 150px"]:
    print("  %-22s %d" % (k, src.count(k)))
