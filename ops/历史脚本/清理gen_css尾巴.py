#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""收尾：删掉 .ge-foot 时代留下的矮屏媒体查询（整页已改为固定高度，这两条规则会打架）。

只做**一处**删除：`@media (max-height: 720px) { ... }` 连同它上面的注释。
删完打印文件尾部，人工核对。
"""
from __future__ import annotations

import io
import re

P = r"_中间产物/线上源码/gen_ui.css"
src = io.open(P, encoding="utf-8").read()
before = src

# 该注释 + 紧随其后的空媒体查询块
pat = re.compile(
    r"/\*[^*]*矮屏[^*]*\*/\s*@media \(max-height: 720px\) \{[^}]*\}\s*",
    re.S,
)
src, n = pat.subn("", src)

print("匹配并删除的块数：%d" % n)
print("行数：%d → %d" % (before.count("\n") + 1, src.count("\n") + 1))
print()
print("=== 删除后文件尾部 ===")
lines = src.split("\n")
for i, ln in enumerate(lines[-22:], start=len(lines) - 21):
    print("%3d| %s" % (i, ln))

print()
print("=== 残留检查（应全为 0）===")
for k in ["ge-foot", "max-height: 720px", "position: sticky", "100vh - 150px", "max-height: 46vh", "max-height: 60vh"]:
    print("  %-22s %d" % (k, src.count(k)))

if n == 1 and "ge-foot" not in src:
    io.open(P, "w", encoding="utf-8", newline="\n").write(src)
    print("\n已写回。")
else:
    print("\n未写回（条件不满足）。")
