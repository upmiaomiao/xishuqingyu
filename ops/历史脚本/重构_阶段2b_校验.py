#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2b 校验：语法 / 漏 import / 循环依赖 / 无用 import。

node --check 默认按 CommonJS 解析，对含 import/export 的文件会误报，
所以先复制成 .mjs 再检查（Node 按扩展名判定模块类型）。
"""
from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

JS = r"_中间产物/重构工作区/frontend/js"
MODS = ["util.js", "message.js", "image.js", "kg.js", "views.js", "store.js", "ask.js", "main.js"]


def code_only(src: str) -> str:
    """去掉注释、字符串字面量、模板字面量的**字面部分**，只留真实代码。

    模板里的 ${...} 是真实代码，要保留（chats/activeId 就出现在里面）。
    """
    out: list[str] = []
    i, n = 0, len(src)
    stack = [["code", 0]]
    while i < n:
        c = src[i]
        mode = stack[-1][0]
        if mode == "code":
            if c == "/" and i + 1 < n and src[i + 1] == "/":
                j = src.find("\n", i)
                i = n if j < 0 else j
                continue
            if c == "/" and i + 1 < n and src[i + 1] == "*":
                j = src.find("*/", i + 2)
                i = n if j < 0 else j + 2
                continue
            if c in "'\"":
                q = c
                i += 1
                while i < n and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
                i += 1
                out.append(" ")
                continue
            if c == "`":
                stack.append(["tmpl", 0])
                i += 1
                out.append(" ")
                continue
            out.append(c)
            i += 1
            continue
        # 模板内
        if c == "\\":
            i += 2
            continue
        if c == "`" and stack[-1][1] == 0:
            stack.pop()
            i += 1
            out.append(" ")
            continue
        if c == "$" and i + 1 < n and src[i + 1] == "{":
            stack[-1][1] += 1
            i += 2
            out.append(" ")
            continue
        if stack[-1][1] > 0:
            if c == "}":
                stack[-1][1] -= 1
                i += 1
                out.append(" ")
                continue
            if c == "{":
                stack[-1][1] += 1
                i += 1
                out.append(c)
                continue
            if c == "`":
                stack.append(["tmpl", 0])
                i += 1
                out.append(" ")
                continue
            out.append(c)
            i += 1
            continue
        i += 1
    return "".join(out)


texts = {m: io.open(os.path.join(JS, m), encoding="utf-8").read() for m in MODS}

# ---- 每个模块声明了哪些顶层名字 ----
declared: dict[str, set[str]] = {}
for m, t in texts.items():
    names: set[str] = set()
    for mm in re.finditer(r"^export\s+(?:async\s+)?function\s+([\w$]+)", t, re.M):
        names.add(mm.group(1))
    for mm in re.finditer(r"^(?:export\s+)?(?:async\s+)?function\s+([\w$]+)", t, re.M):
        names.add(mm.group(1))
    for mm in re.finditer(r"^(?:export\s+)?(?:const|let|var)\s+(.*?)(?:=|;|$)", t, re.M):
        for part in mm.group(1).split(","):
            nm = re.match(r"\s*([\w$]+)", part)
            if nm:
                names.add(nm.group(1))
    declared[m] = names

all_names = set().union(*declared.values())

# 本模块**内部**声明的名字（函数参数、函数体内的 const/let、catch 参数等）。
# 不做这个，就会把 `const q = input.value` 这类局部变量误报成"漏 import"。
local_decl: dict[str, set[str]] = {}
for m, t in texts.items():
    s: set[str] = set()
    for mm in re.finditer(r"\b(?:const|let|var)\s+([\w$]+)", t):
        s.add(mm.group(1))
    for mm in re.finditer(r"\b(?:const|let|var)\s+([\w$]+)\s*=", t):
        s.add(mm.group(1))
    # 多声明符续行：const a = 1,\n  b = 2;  —— 不认这个就会把 b 误报成"漏 import"
    for mm in re.finditer(r",\s*\n?\s*([\w$]+)\s*=", t):
        s.add(mm.group(1))
    # 函数参数（含箭头函数单参、解构粗判）
    for mm in re.finditer(r"function\s*[\w$]*\s*\(([^)]*)\)", t):
        for part in mm.group(1).split(","):
            nm = re.match(r"\s*([\w$]+)", part)
            if nm:
                s.add(nm.group(1))
    for mm in re.finditer(r"\(([^()]*)\)\s*=>", t):
        for part in mm.group(1).split(","):
            nm = re.match(r"\s*([\w$]+)", part)
            if nm:
                s.add(nm.group(1))
    for mm in re.finditer(r"catch\s*\(\s*([\w$]+)", t):
        s.add(mm.group(1))
    local_decl[m] = s

# ---- 每个模块 import 了什么 ----
imported: dict[str, dict[str, str]] = {}
graph: dict[str, set[str]] = {}
for m, t in texts.items():
    imported[m] = {}
    graph[m] = set()
    for mm in re.finditer(r"^import\s*\{([^}]*)\}\s*from\s*'\./([\w.]+)'", t, re.M):
        names = [x.strip() for x in mm.group(1).split(",") if x.strip()]
        src = mm.group(2)
        graph[m].add(src)
        for nm in names:
            imported[m][nm] = src

print("=" * 84)
print("① 语法（复制成 .mjs 后用 node --check）")
print("=" * 84)
tmp = os.path.join(JS, "_mjscheck")
shutil.rmtree(tmp, ignore_errors=True)
os.makedirs(tmp, exist_ok=True)
ok_all = True
for m in MODS:
    dst = os.path.join(tmp, m.replace(".js", ".mjs"))
    shutil.copyfile(os.path.join(JS, m), dst)
    r = subprocess.run(["node", "--check", dst], capture_output=True, text=True)
    ok = r.returncode == 0
    ok_all &= ok
    print("  %-12s %s" % (m, "√" if ok else "✗ " + (r.stderr or "")[:200]))
if not ok_all:
    print("\n语法不过，终止")
    sys.exit(1)

print()
print("=" * 84)
print("② 漏 import（用到了别人家的顶层名字，却没 import）")
print("=" * 84)
bad = 0
for m in MODS:
    code = code_only(texts[m])
    # 去掉本模块的声明行，避免自己声明自己算引用
    own = declared[m] | local_decl[m]
    for n in sorted(all_names):
        if n in own or n in imported[m]:
            continue
        # 本模块内是否也局部声明了同名（函数参数、内部 const 等）——粗判：出现次数 > 0 且非属性
        if re.search(r"(?<![.\w$])" + re.escape(n) + r"(?![\w$])", code):
            owner = next((mm for mm in MODS if n in declared[mm]), "?")
            print("  ✗ %-12s 用了 %-24s（属于 %s）却没 import" % (m, n, owner))
            bad += 1
print("  %s" % ("★ 无漏 import" if bad == 0 else "共 %d 处" % bad))

print()
print("=" * 84)
print("③ 循环依赖")
print("=" * 84)
for m in MODS:
    print("  %-12s → %s" % (m, ", ".join(sorted(graph[m])) or "（无）"))
color: dict[str, int] = {}
cyc: list[list[str]] = []


def dfs(u: str, path: list[str]) -> None:
    color[u] = 1
    for v in sorted(graph.get(u, ())):
        if color.get(v, 0) == 1:
            cyc.append(path[path.index(v):] + [v] if v in path else [u, v])
        elif color.get(v, 0) == 0:
            dfs(v, path + [v])
    color[u] = 2


for m in MODS:
    if color.get(m, 0) == 0:
        dfs(m, [m])
print("  %s" % ("★ 无环" if not cyc else "✗ 发现环：%s" % cyc))

print()
print("=" * 84)
print("④ 无用 import")
print("=" * 84)
unused = 0
for m in MODS:
    code = code_only(texts[m])
    for n, src in imported[m].items():
        if not re.search(r"(?<![.\w$])" + re.escape(n) + r"(?![\w$])", code):
            print("  ! %-12s 从 %s import 了 %s，但没用到" % (m, src, n))
            unused += 1
print("  %s" % ("★ 无无用 import" if unused == 0 else "共 %d 处（可删）" % unused))

print()
print("=" * 84)
print("⑤ 规模")
print("=" * 84)
tot = 0
for m in MODS:
    n = texts[m].count("\n") + 1
    tot += n
    flag = "  ← 超过 500 行，建议再拆" if n > 500 else ""
    print("  %-12s %4d 行%s" % (m, n, flag))
print("  合计 %d 行（原内联脚本 852 行）" % tot)

shutil.rmtree(tmp, ignore_errors=True)
if bad or cyc:
    sys.exit(1)
