#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拆解 index.html 的结构：不读全文，只出骨架，用于规划拆分。"""
from __future__ import annotations

import io
import re

P = r"_中间产物/重构工作区/frontend/index.html"
h = io.open(P, encoding="utf-8").read()
lines = h.split("\n")

print("=" * 78)
print("① HTML 骨架（去掉 style/script 内容后剩下的标签行）")
print("=" * 78)
# 把 style/script 内容挖掉
stripped = re.sub(r"(<style[^>]*>).*?(</style>)", r"\1 …\2", h, flags=re.S)
stripped = re.sub(r"(<script[^>]*>).*?(</script>)", r"\1 …\2", stripped, flags=re.S)
for i, l in enumerate(stripped.split("\n"), 1):
    t = l.strip()
    if t:
        print("  %3d| %s" % (i, t[:150]))

print()
print("=" * 78)
print("② 两个 <style> 块的选择器清单")
print("=" * 78)
for bi, m in enumerate(re.finditer(r"<style[^>]*>(.*?)</style>", h, re.S), 1):
    css = m.group(1)
    start_line = h[:m.start()].count("\n") + 1
    end_line = h[:m.end()].count("\n") + 1
    sels = re.findall(r"([^{}]+)\{", css)
    print("  --- 第 %d 块（第 %d–%d 行，%d 字节）%d 条规则 ---"
          % (bi, start_line, end_line, len(css.encode()), len(sels)))
    for s in sels:
        s = " ".join(s.split())
        if s:
            print("      %s" % s[:110])

print()
print("=" * 78)
print("③ <script> 块里的函数清单")
print("=" * 78)
m = re.search(r"<script[^>]*>(.*?)</script>", h, re.S)
js = m.group(1)
base_line = h[:m.start()].count("\n") + 1
fns = re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js)
print("  函数 %d 个：" % len(fns))
for i in range(0, len(fns), 4):
    print("      " + "  ".join("%-24s" % f for f in fns[i:i + 4]))

print()
print("=" * 78)
print("④ 顶层语句（判断初始化逻辑有哪些）")
print("=" * 78)
# 顶层：不以空白开头的行
tops = []
for l in js.split("\n"):
    if l and not l[0].isspace():
        tops.append(" ".join(l.split())[:120])
for t in tops:
    print("      %s" % t)

print()
print("=" * 78)
print("⑤ 关键 DOM id / 全局引用")
print("=" * 78)
ids_html = sorted(set(re.findall(r'id="([^"]+)"', h)))
print("  HTML 里定义的 id（%d 个）：" % len(ids_html))
for i in range(0, len(ids_html), 6):
    print("      " + "  ".join("%-18s" % x for x in ids_html[i:i + 6]))
ids_js = sorted(set(re.findall(r'\$\("([^"]+)"\)|getElementById\("([^"]+)"\)', js) and
                    [a or b for a, b in re.findall(r'\$\("([^"]+)"\)|getElementById\("([^"]+)"\)', js)]))
print("  JS 里引用的 id（%d 个）：" % len(ids_js))
for i in range(0, len(ids_js), 6):
    print("      " + "  ".join("%-18s" % x for x in ids_js[i:i + 6]))
missing = [x for x in ids_js if x not in ids_html]
print("  ★ JS 引用但 HTML 里没有的：%s" % (missing or "无"))
