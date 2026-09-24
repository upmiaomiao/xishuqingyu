#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2b 等价性证明：逐条目对比「原内联脚本」与「拆出的模块」。

归一化后逐条比对，只允许出现**已声明的那几处结构性改动**：
  · chats / activeId  ->  state.chats / state.activeId
  · export 前缀（新增）
  · busy 由顶层 let 搬进 ask.js 模块私有
  · 状态声明 let chats,activeId,busy -> export const state = {...}
  · IIFE（原 120-137）被 main.js 显式包装替代

任何其它差异都会被抓出来。
"""
from __future__ import annotations

import io
import os
import re
import sys

ORIG = r"_中间产物/重构工作区/frontend/_app_pretty.js"
JS = r"_中间产物/重构工作区/frontend/js"
MODS = ["util.js", "message.js", "image.js", "kg.js", "views.js", "store.js", "ask.js", "main.js"]

orig_lines = io.open(ORIG, encoding="utf-8").read().split("\n")
CLOSE = re.compile(r"^[}\])]")


def is_start(l: str) -> bool:
    return bool(l) and not l[0].isspace() and not CLOSE.match(l)


starts = [i for i, l in enumerate(orig_lines) if is_start(l)]
orig_items: dict[int, str] = {}
for k, s in enumerate(starts):
    e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(orig_lines) - 1
    orig_items[s + 1] = "\n".join(orig_lines[s:e + 1])


REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>") | {"\n"}


def strip_comments(t: str) -> str:
    """去注释。**必须认正则字面量** —— 否则 /[&<>"']/g 里的引号会被当成字符串起始，
    把后面一大段代码吞掉（我第一版就栽在这，误报了 esc/formatAnswer/onPickImage 三条）。"""
    out, i, n = [], 0, len(t)
    prev = "\n"
    while i < n:
        c = t[i]
        if c == "/" and i + 1 < n and t[i + 1] == "/":
            j = t.find("\n", i)
            i = n if j < 0 else j
            continue
        if c == "/" and i + 1 < n and t[i + 1] == "*":
            j = t.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        if c == "/" and prev in REGEX_PREV:
            # 正则字面量：抄到未转义的 / 为止（含字符类 [...] 内的 /）
            out.append(c)
            i += 1
            in_class = False
            while i < n:
                ch = t[i]
                if ch == "\\":
                    out.append(ch)
                    i += 1
                    if i < n:
                        out.append(t[i])
                        i += 1
                    continue
                if ch == "[":
                    in_class = True
                elif ch == "]":
                    in_class = False
                elif ch == "/" and not in_class:
                    out.append(ch)
                    i += 1
                    break
                elif ch == "\n":
                    break
                out.append(ch)
                i += 1
            prev = "/"
            continue
        if c in "'\"`":
            q = c
            out.append(c)
            i += 1
            while i < n and t[i] != q:
                if t[i] == "\\":
                    out.append(t[i])
                    i += 1
                out.append(t[i])
                i += 1
            out.append(q)
            i += 1
            prev = q
            continue
        out.append(c)
        if not c.isspace():
            prev = c
        i += 1
    return "".join(out)


def norm(t: str) -> str:
    t = strip_comments(t)
    t = re.sub(r"^export\s+", "", t, flags=re.M)
    t = re.sub(r"(?<![.\w$])chats(?![\w$])", "state.chats", t)
    t = re.sub(r"(?<![.\w$])activeId(?![\w$])", "state.activeId", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


mod_texts = {m: io.open(os.path.join(JS, m), encoding="utf-8").read() for m in MODS}
all_mod = "\n".join(mod_texts[m] for m in MODS)

DROPPED = {120: "monkey-patch IIFE，改由 main.js 显式包装"}
SPECIAL = {
    2: "let chats,activeId,busy -> export const state = {chats,activeId}；busy 移入 ask.js",
}

print("=" * 92)
print("逐条目等价性比对（%d 个条目）" % len(orig_items))
print("=" * 92)
same = diff = 0
problems: list[str] = []
for ln in sorted(orig_items):
    o = orig_items[ln]
    if ln in DROPPED:
        print("  ~ 行 %-4d 跳过：%s" % (ln, DROPPED[ln]))
        continue
    if ln in SPECIAL:
        print("  ~ 行 %-4d 跳过：%s" % (ln, SPECIAL[ln]))
        continue
    on = norm(o)
    if not on:
        # 纯注释条目：norm() 会把它清空，而空串恒为任何串的子串 —— 会**假通过**。
        # 所以这里改成核对原文是否逐字保留。
        if o.strip() in all_mod:
            same += 1
            print("  · 行 %-4d 注释条目，原文逐字保留" % ln)
        else:
            diff += 1
            print("  ✗ 行 %-4d 注释丢失：%s" % (ln, " ".join(o.split())[:60]))
        continue
    if on in norm(all_mod):
        same += 1
        continue
    # 允许「删掉了一行 closeKnowledgeGraph();」的两种条目
    if re.sub(r"\s*closeKnowledgeGraph\(\);", "", on) in re.sub(r"\s*closeKnowledgeGraph\(\);", "", norm(all_mod)):
        same += 1
        print("  ~ 行 %-4d 差异仅在于 closeKnowledgeGraph()（有意为之）" % ln)
        continue
    diff += 1
    problems.append((ln, o))
    head = " ".join(o.split())[:70]
    print("  ✗ 行 %-4d 未匹配：%s" % (ln, head))
    # 打印第一个差异位置，方便定位
    nm = norm(all_mod)
    lo, hi = 0, min(len(on), len(nm))
    while lo < hi and on[lo] == nm[lo]:
        lo += 1
    print("        首个差异在第 %d 字符：" % lo)
    print("          原：...%s..." % on[max(0, lo - 40):lo + 70])
    print("          新：...%s..." % nm[max(0, lo - 40):lo + 70])

print()
print("  匹配 %d / 有差异 %d / 跳过 %d" % (same, diff, len(DROPPED) + len(SPECIAL)))

print()
print("=" * 92)
print("函数清单核对（原 42 个函数是否都在模块里）")
print("=" * 92)
fns = re.findall(r"^(?:async\s+)?function\s+([\w$]+)", "\n".join(orig_items.values()), re.M)
fns = sorted(set(fns))
miss = []
for f in fns:
    if not re.search(r"^(?:export\s+)?(?:async\s+)?function\s+" + re.escape(f) + r"\b",
                     all_mod, re.M):
        miss.append(f)
print("  原函数 %d 个，模块里缺失 %s" % (len(fns), miss or "无"))

print()
print("=" * 92)
print("顶层声明核对（原 let/const 名字是否都还在）")
print("=" * 92)
decls = set()
for o in orig_items.values():
    mm = re.match(r"(?:const|let|var)\s+(.*?)(?:=|;|$)", o, re.S)
    if mm and "function" not in o[:20]:
        for part in mm.group(1).split(","):
            nm = re.match(r"\s*([\w$]+)", part)
            if nm:
                decls.add(nm.group(1))
decls -= {"chats", "activeId", "busy"}  # 有意改造
gone = [d for d in sorted(decls)
        if not re.search(r"(?<![.\w$])" + re.escape(d) + r"(?![\w$])", all_mod)]
print("  原顶层声明 %d 个（已排除 chats/activeId/busy），模块里找不到的：%s"
      % (len(decls), gone or "无"))

print()
print("=" * 92)
print("state 改造核对")
print("=" * 92)
print("  util.js 里 state 对象：%s"
      % ("有" if re.search(r"export const state = \{ chats: \[\], activeId: '' \};", mod_texts["util.js"]) else "✗ 没有"))
print("  残留的裸 chats / activeId（应为 0，state 对象里的属性键不算）：%d"
      % len(re.findall(r"(?<![.\w$])(?:chats|activeId)(?![\w$])(?!\s*:)", all_mod)))
print("  ask.js 里 busy 模块私有：%s"
      % ("有" if re.search(r"^let busy = false;", mod_texts["ask.js"], re.M) else "✗ 没有"))

print()
print("=" * 92)
print("window 契约核对（HTML onclick 用到的函数是否都暴露了）")
print("=" * 92)
html = io.open(r"_中间产物/重构工作区/frontend/index.html.新", encoding="utf-8").read()
need = set(re.findall(r'on(?:click|change|input)\s*=\s*["\']([\w$]+)\s*\(', html))
need |= set(re.findall(r'on(?:click|change|input)\s*=\s*["\']([\w$]+)\(', all_mod))
api_block = mod_texts["main.js"]
missing = sorted(n for n in need if not re.search(r"(?<![\w$])" + re.escape(n) + r"(?![\w$])", api_block))
print("  HTML/JS 里 onclick 调用的函数 %d 个：%s" % (len(need), ", ".join(sorted(need))))
print("  main.js 未暴露的：%s" % (missing or "无"))

bad = diff or miss or gone or missing
print()
print("=" * 92)
print("结论：%s" % ("★ 等价性通过" if not bad else "✗ 有 %d 类问题待查" % sum(1 for x in (diff, miss, gone, missing) if x)))
print("=" * 92)
sys.exit(1 if bad else 0)
