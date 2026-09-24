#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3：var -> const/let 的作用域安全性分析。

风险：var 是**函数作用域**，let/const 是**块作用域**。
  if (x) { var a = 1; }
  use(a);            // var：能用；let：ReferenceError
另外 var 会提升，let 不会：
  use(b); var b = 2; // var：undefined；let：ReferenceError

所以不能无脑替换。这里逐个 var 判断：
  · 声明是否在块里（相对所属函数体）
  · 名字是否在「最内层包围块」之外被使用
  · 名字是否在声明之前被使用
  · 名字是否被重新赋值（决定 const 还是 let）
"""
from __future__ import annotations

import io
import re

FILES = {
    "gen_ui.js": r"_中间产物/重构工作区/xishu_pipeline/static/gen_ui.js",
    "audit_ui.js": r"_中间产物/重构工作区/xishu_pipeline/static/audit_ui.js",
}


def scan(src: str):
    """返回 (code, kinds)：code 是去掉字符串/注释/正则后的等长文本（用空格填充），
    kinds[i] 是该字符的类别：'c'=代码，'s'=字符串/注释/正则内部。"""
    n = len(src)
    kinds = ["c"] * n
    i = 0
    prev = "\n"
    REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>") | {"\n"}
    while i < n:
        c = src[i]
        if c == "/" and i + 1 < n and src[i + 1] == "/":
            j = src.find("\n", i)
            j = n if j < 0 else j
            for k in range(i, j):
                kinds[k] = "s"
            i = j
            continue
        if c == "/" and i + 1 < n and src[i + 1] == "*":
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for k in range(i, min(j, n)):
                kinds[k] = "s"
            i = j
            continue
        if c == "/" and prev in REGEX_PREV:
            j = i + 1
            in_class = False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    j += 2
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    j += 1
                    break
                elif ch == "\n":
                    break
                j += 1
            for k in range(i, min(j, n)):
                kinds[k] = "s"
            i = j
            prev = "/"
            continue
        if c in "'\"`":
            q = c
            j = i + 1
            while j < n and src[j] != q:
                if src[j] == "\\":
                    j += 1
                j += 1
            j += 1
            for k in range(i, min(j, n)):
                kinds[k] = "s"
            i = j
            prev = q
            continue
        if not c.isspace():
            prev = c
        i += 1
    code = "".join(src[k] if kinds[k] == "c" else " " for k in range(n))
    return code, kinds


for name, path in FILES.items():
    src = io.open(path, encoding="utf-8").read()
    code, _kinds = scan(src)

    # 每个字符位置 -> 所属的最内层 { } 区间
    stack: list[int] = []
    open_at: dict[int, int] = {}   # 位置 -> 当前栈深
    depth_of = [0] * len(code)
    for i, ch in enumerate(code):
        depth_of[i] = len(stack)
        if ch == "{":
            stack.append(i)
        elif ch == "}":
            if stack:
                stack.pop()

    # 函数体起点：粗略用 "function" 关键字后的第一个 { 的下一层
    vars_found = []
    for m in re.finditer(r"(?<![.\w$])var\s+([\w$]+)", code):
        nm = m.group(1)
        pos = m.start()
        d = depth_of[pos]
        # 该名字的所有出现位置（代码区、独立标识符）
        uses = [mm.start() for mm in re.finditer(r"(?<![.\w$])" + re.escape(nm) + r"(?![\w$])", code)]
        # 赋值位置（= += -= ++ -- 或 .push 等变异）
        assigns = [mm.start() for mm in re.finditer(
            r"(?<![.\w$])" + re.escape(nm) + r"\s*(?:=(?!=)|\+=|-=|\*=|/=|\+\+|--)", code)]
        # 声明之前是否被使用
        before = [u for u in uses if u < pos]
        # 是否在「更浅的深度」被使用（= 逃出了声明所在的块）
        escaped = [u for u in uses if depth_of[u] < d]
        vars_found.append((nm, pos, d, len(uses), len(assigns), len(before), len(escaped),
                           src[:pos].count("\n") + 1))

    print("=" * 96)
    print("%s：var 声明 %d 个" % (name, len(vars_found)))
    print("=" * 96)
    print("  %-16s %-6s %-5s %-6s %-6s %-7s %-8s %s"
          % ("名字", "行", "块深", "出现", "赋值", "声明前用", "逃出块", "结论"))
    n_const = n_let = n_unsafe = 0
    for nm, pos, d, uses, assigns, before, escaped, ln in vars_found:
        if escaped or before:
            verdict = "✗ 不安全，保留 var"
            n_unsafe += 1
        elif assigns:
            verdict = "let（有重新赋值）"
            n_let += 1
        else:
            verdict = "const（无重新赋值）"
            n_const += 1
        print("  %-16s %-6d %-5d %-6d %-6d %-7d %-8d %s"
              % (nm, ln, d, uses, assigns, before, escaped, verdict))
    print()
    print("  结论：const %d 个，let %d 个，不安全需保留 var %d 个" % (n_const, n_let, n_unsafe))
    print()
