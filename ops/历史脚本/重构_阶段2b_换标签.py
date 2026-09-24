#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2b-3：把 index.html 的内联 <script> 换成 <script type="module" src="/static/js/main.js">。

只动这一处；其余字节保持原样。
"""
from __future__ import annotations

import hashlib
import io
import re
import sys

SRC = r"_中间产物/重构工作区/frontend/index.html.新"

html = io.open(SRC, encoding="utf-8").read()
before = len(html.encode())
before_md5 = hashlib.md5(html.encode()).hexdigest()

ms = list(re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S))
assert len(ms) == 1, "预期恰好 1 个内联 script，实际 %d" % len(ms)
m = ms[0]
js = m.group(1)

# 内联脚本必须与已拆出的 _app_pretty.js 同源（防止拆的是旧版本）
raw = io.open(r"_中间产物/重构工作区/frontend/_app_raw.js", encoding="utf-8").read()
assert js == raw, "内联脚本与 _app_raw.js 不一致，先重跑抽取"

new_tag = '<script type="module" src="/static/js/main.js"></script>'
html2 = html[:m.start()] + new_tag + html[m.end():]

# 只允许这一处变化
assert html2.count("<script") == 1, "改动后 script 标签数应为 1，实际 %d" % html2.count("<script")
assert "<style" not in html2, "还有内联 style"
assert html2 != html

io.open(SRC, "w", encoding="utf-8", newline="\n").write(html2)
after = len(html2.encode())

print("index.html：%d 字节 → %d 字节（减 %d）" % (before, after, before - after))
print("  md5 %s → %s" % (before_md5, hashlib.md5(html2.encode()).hexdigest()))
print("  被替换的内联脚本：%d 字节" % len(js.encode()))
print("  新标签：%s" % new_tag)
print()
print("  剩余内联 <script>：%d 个" % len(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html2)))
print("  外链 <script>：%d 个" % len(re.findall(r"<script[^>]*\bsrc=", html2)))
print("  <link> 数：%d" % len(re.findall(r"<link\b", html2)))
print("  最长行：%d 字符" % max(len(l) for l in html2.split("\n")))
