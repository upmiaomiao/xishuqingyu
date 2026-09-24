#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把压成一行的 index.html 抽成"标签树 + 行号"，便于看懂结构。

index.html 是被压缩过的（162 行里有 997 字符的长行），直接读看不懂层级。
这里只解析**标签结构**（不看样式内容和脚本逻辑），打印 id/class 与所在行号。
"""
from __future__ import annotations

import pathlib
import re
import sys

P = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                 r"_中间产物/重构工作区/frontend/index.html")
src = P.read_text(encoding="utf-8")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}

# 逐字符扫描，跳过 <style> / <script> 内容
i = 0
line = 1
depth = 0
out: list[str] = []
stack: list[str] = []

while i < len(src):
    ch = src[i]
    if ch == "\n":
        line += 1
        i += 1
        continue
    if ch != "<":
        i += 1
        continue

    # 注释
    if src.startswith("<!--", i):
        end = src.find("-->", i)
        end = len(src) - 3 if end < 0 else end
        tag_text = src[i:end + 3]
        out.append("%s<!-- %s -->" % ("  " * depth, tag_text[4:-3].strip()[:70]))
        line += src.count("\n", i, end + 3)
        i = end + 3
        continue

    end = src.find(">", i)
    if end < 0:
        break
    tag = src[i:end + 1]
    line += src.count("\n", i, end + 1)
    i = end + 1

    m = re.match(r"</\s*([a-zA-Z0-9]+)", tag)
    if m:
        name = m.group(1).lower()
        if stack and stack[-1] == name:
            stack.pop()
            depth = max(0, depth - 1)
        out.append("%s</%s>" % ("  " * depth, name))
        continue

    m = re.match(r"<\s*([a-zA-Z0-9]+)", tag)
    if not m:
        continue
    name = m.group(1).lower()

    # 跳过 style/script 的整块内容
    if name in ("style", "script"):
        close = src.find("</%s>" % name, i)
        if close < 0:
            break
        inner_lines = src.count("\n", i, close)
        kind = "样式" if name == "style" else "脚本"
        out.append("%s<%s>  【%s %d 行，已跳过】" % ("  " * depth, name, kind, inner_lines + 1))
        line += inner_lines
        i = close + len(name) + 3
        continue

    attrs = ""
    for a in ("id", "class", "type", "placeholder", "value", "hidden"):
        am = re.search(r'\b%s\s*=\s*"([^"]*)"' % a, tag)
        if am:
            v = am.group(1)
            if a == "class" and len(v) > 34:
                v = v[:34] + "…"
            attrs += ' %s="%s"' % (a, v)

    self_close = tag.rstrip().endswith("/>") or name in VOID
    out.append("%s<%s%s>%s" % ("  " * depth, name, attrs,
                               "  ← 第 %d 行" % line if attrs else ""))
    if not self_close:
        stack.append(name)
        depth += 1

print("=" * 100)
print("index.html 结构（只列带 id/class 的元素与层级）")
print("=" * 100)
for ln in out:
    # 只打印有属性的行 + 它们的父级缩进提示
    if "id=" in ln or "class=" in ln or "<!--" in ln or "【" in ln or "</" in ln:
        print(ln)
