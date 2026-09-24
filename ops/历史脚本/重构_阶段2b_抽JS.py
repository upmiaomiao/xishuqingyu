#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2b-1：把 index.html 的 <script> 抽出来（逐字节原样），交给 prettier 格式化。

不自己写 JS 美化器 —— prettier 是基于解析器的，语义保持由构造保证；
我上一版手写 CSS 美化器就把注释写漏了闭合，JS 的坑只会更多（正则字面量、模板串、ASI）。
"""
from __future__ import annotations

import io
import re
import sys

SRC = r"_中间产物/重构工作区/frontend/index.html.新"
DST = r"_中间产物/重构工作区/frontend/_app_raw.js"

html = io.open(SRC, encoding="utf-8").read()
ms = list(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S))
assert len(ms) == 1, "预期恰好 1 个内联 script，实际 %d" % len(ms)
js = ms[0].group(1)
start_line = html[:ms[0].start()].count("\n") + 1
end_line = html[:ms[0].end()].count("\n") + 1

print("内联 <script>：第 %d–%d 行，%d 字节，%d 行，最长行 %d 字符"
      % (start_line, end_line, len(js.encode()), js.count("\n") + 1,
         max(len(l) for l in js.split("\n"))))
print("前 200 字：%r" % js[:200])
print("后 120 字：%r" % js[-120:])

io.open(DST, "w", encoding="utf-8", newline="\n").write(js)
print()
print("已写 %s（%d 字节）" % (DST, len(js.encode())))
