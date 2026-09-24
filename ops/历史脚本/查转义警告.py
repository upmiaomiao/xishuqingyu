#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼 resilience.py 那行正则在底层到底是什么字符。

背景：语法检查报 `SyntaxWarning: invalid escape sequence '\\['`，
但那行明明是 r"..." 原始字符串。原始字符串里不该报这个 ——
除非字符串中途被 ASCII 双引号**截断**了，
后面那段就变成了普通字符串，`\\[` 于是成了无效转义。
"""
import io

p = "_中间产物/重构工作区/xishu_pipeline/resilience.py"
lines = io.open(p, encoding="utf-8").read().splitlines()
s = lines[157]

print("第 158 行原样：")
print(s)
print()
print("repr：")
print(repr(s))
print()
print("ASCII 双引号 (0x22) 出现次数：", s.count(chr(0x22)))
print("全角左引号 U+201C：", s.count(chr(0x201C)))
print("全角右引号 U+201D：", s.count(chr(0x201D)))
print("全角单引号 U+2018/U+2019：", s.count(chr(0x2018)), s.count(chr(0x2019)))
print("ASCII 单引号 (0x27)：", s.count(chr(0x27)))
print()
print("逐字符（只打非常规的）：")
for i, ch in enumerate(s):
    o = ord(ch)
    if o > 127 or ch in ('"', "'", "\\"):
        print("   [%3d] U+%04X %r" % (i, o, ch))

print()
print("=== 验证：把它当 Python 字面量求值，看实际编译出几个字符串 ===")
import ast
tree = ast.parse(s)
node = tree.body[0].value
print("  表达式类型：", type(node).__name__)
if isinstance(node, ast.Constant):
    print("  单个常量，值：", repr(node.value)[:160])
elif isinstance(node, ast.BinOp):
    print("  ★ 是拼接运算，说明源码里写了 + 号")
elif isinstance(node, ast.JoinedStr):
    print("  ★ 是 f-string")
else:
    print("  ★ 是隐式拼接的多个字符串字面量 —— 这就是警告的来源")
    print("  片段数：", len(node.values))
    for i, v in enumerate(node.values):
        print("    片段 %d: %r" % (i, v.value))
