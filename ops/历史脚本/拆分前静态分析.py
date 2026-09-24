#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拆分前静态分析：跨模块引用 + 可变状态风险点。

ES 模块的硬约束：**不能给 import 进来的绑定赋值**（SyntaxError）。
而原代码里 chats / activeId / busy 是被多个函数反复赋值的顶层 let，
拆模块后它们必须收进一个 state 对象，用 state.chats = ... 的形式改。
"""
from __future__ import annotations

import io
import re
from collections import defaultdict

P = r"_中间产物/重构工作区/frontend/_app_pretty.js"
src = io.open(P, encoding="utf-8").read()
lines = src.split("\n")

CLOSE = re.compile(r"^[}\])]")


def is_start(l: str) -> bool:
    return bool(l) and not l[0].isspace() and not CLOSE.match(l)


starts = [i for i, l in enumerate(lines) if is_start(l)]
items = []
for k, s in enumerate(starts):
    e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(lines) - 1
    items.append((s + 1, e + 1))  # 1-based

# ---- 每条目声明的顶层名字 ----
decl_of: dict[int, list[str]] = {}
for s, e in items:
    text = "\n".join(lines[s - 1:e])
    names: list[str] = []
    m = re.match(r"(?:async\s+)?function\s+([\w$]+)", text)
    if m:
        names = [m.group(1)]
    else:
        m2 = re.match(r"(?:const|let|var)\s+(.*?)(?:=|;|$)", text, re.S)
        if m2:
            for part in m2.group(1).split(","):
                nm = re.match(r"\s*([\w$]+)", part)
                if nm:
                    names.append(nm.group(1))
    decl_of[s] = names

# ---- 模块归属（按条目起始行）----
MODULES: dict[str, list[int]] = {
    "util.js":    [1, 2, 5, 10, 482],
    "store.js":   [456, 467, 485, 496, 502, 510, 625],
    "message.js": [518, 521, 577, 580, 602, 618, 629, 638, 642, 645],
    "ask.js":     [648],
    "image.js":   [763, 764, 765, 767, 771, 779, 787, 800, 832],
    "kg.js":      [13, 29, 164, 181, 201, 329, 368, 372, 375, 388, 397, 398,
                   407, 425, 433, 434, 435, 449, 452],
    "views.js":   [36, 47, 54, 66, 72, 73, 89, 95, 119, 120, 138, 140],
    "main.js":    [840, 841, 845, 851],
}

assigned = sorted(x for ls in MODULES.values() for x in ls)
all_starts = [s for s, _e in items]
missing = [s for s in all_starts if s not in assigned]
extra = [s for s in assigned if s not in all_starts]
print("条目归属校验：未分配 %s / 多分配 %s" % (missing or "无", extra or "无"))
dup = [s for s in assigned if assigned.count(s) > 1]
print("重复分配：%s" % (set(dup) or "无"))

# ---- 名字 -> 所属模块 ----
owner: dict[str, str] = {}
for mod, ls in MODULES.items():
    for s in ls:
        for n in decl_of.get(s, []):
            owner[n] = mod
print()
print("顶层名字共 %d 个，分属：" % len(owner))
by_mod = defaultdict(list)
for n, m in owner.items():
    by_mod[m].append(n)
for m in MODULES:
    print("  %-12s %s" % (m, ", ".join(by_mod[m])))

# ---- 跨模块引用 ----
print()
print("=" * 88)
print("跨模块引用（每个模块需要用到的、别人家的名字）")
print("=" * 88)
mod_text: dict[str, str] = {}
for mod, ls in MODULES.items():
    mod_text[mod] = "\n".join("\n".join(lines[s - 1:e]) for s, e in items if s in ls)

needs: dict[str, dict[str, list[str]]] = {}
for mod, text in mod_text.items():
    need: dict[str, list[str]] = defaultdict(list)
    for n, om in owner.items():
        if om == mod:
            continue
        # 作为独立标识符出现，且前面不是 . （排除属性访问）
        if re.search(r"(?<![.\w$])" + re.escape(n) + r"(?![\w$])", text):
            need[om].append(n)
    needs[mod] = dict(need)
    if need:
        for om, ns in sorted(need.items()):
            print("  %-12s ← %-12s %s" % (mod, om, ", ".join(sorted(ns))))
    else:
        print("  %-12s （无外部依赖）" % mod)

# ---- 可变状态风险 ----
print()
print("=" * 88)
print("可变状态风险：给顶层 let 赋值的次数（跨模块赋值 = SyntaxError）")
print("=" * 88)
for var in ("chats", "activeId", "busy", "pendingImage"):
    assign_sites = []
    for m, _ln in re.finditer(r"(?<![.\w$])" + var + r"\s*(?:=(?!=)|\+\+|--|\.push|\.unshift|\.splice|\.filter)", src):
        ln = src[:m.start()].count("\n") + 1
        mod = next((mm for mm, ls in MODULES.items()
                    if any(s <= ln <= e for s, e in items if s in ls)), "?")
        assign_sites.append((ln, mod))
    mods = sorted(set(m for _l, m in assign_sites))
    print("  %-14s 赋值/变异 %2d 处，涉及模块 %s" % (var, len(assign_sites), mods))

print()
print("  ★ 需要收进 state 对象的变量（跨模块被赋值的）：")
for var in ("chats", "activeId", "busy"):
    mods = sorted(set(m for ln, m in
                      [(src[:m.start()].count("\n") + 1,
                        next((mm for mm, ls in MODULES.items()
                              if any(s <= src[:m.start()].count("\n") + 1 <= e for s, e in items if s in ls)), "?"))
                       for m in re.finditer(r"(?<![.\w$])" + var + r"\s*(?:=(?!=)|\+\+|--)", src)]))
    print("      %-10s 在 %s 里被赋值 %s" % (var, mods, "→ 必须用 state" if len(mods) > 1 else "→ 模块内私有即可"))

# ---- 属性访问冲突检查 ----
print()
print("=" * 88)
print("文本替换风险：这些名字有没有以「属性」形式出现（.chats / chats: ）")
print("=" * 88)
for var in ("chats", "activeId", "busy", "pendingImage"):
    dot = len(re.findall(r"\." + var + r"(?![\w$])", src))
    key = len(re.findall(r"(?<![\w$])" + var + r"\s*:", src))
    print("  %-14s .%s 出现 %d 次；作为对象键 %s: 出现 %d 次" % (var, var, dot, var, key))
