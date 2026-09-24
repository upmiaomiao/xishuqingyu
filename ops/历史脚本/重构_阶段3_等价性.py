#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3 等价性证明：ES 模块化改造是否无损。

做法：把改造前的 .varfix.js 按**同一套规则**独立归一化（去外壳、去 use strict、
去 window 赋值、去缩进、应用文本修正），再和改造后的文件逐字比对。
归一化由这份脚本自己实现，不复用改造脚本的逻辑 —— 否则等于自己证明自己。
"""
from __future__ import annotations

import io
import re
import sys

W = r"_中间产物/重构工作区/xishu_pipeline/static"

REGEX_PREV = set("(,=:[!&|?{};+-*%~^<>") | {"\n"}


def strip_comments(t: str) -> str:
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
    t = re.sub(r"\s+", " ", t)
    return t.strip()


SPECS = [
    {
        "name": "gen_ui.js",
        "drops": ["window.mountGenUI = mountGenUI;", "window.setGenEmbedded = setEmbedded;"],
        "fixes": [('String(s == null ? "" : s)', 'String(s ?? "")')],
    },
    {
        "name": "audit_ui.js",
        "drops": ["window.mountAuditUI = mountAuditUI;"],
        "fixes": [],
    },
]

ok_all = True
for sp in SPECS:
    name = sp["name"]
    before = io.open("%s/%s" % (W, name.replace(".js", ".varfix.js")), encoding="utf-8").read()
    after = io.open("%s/%s" % (W, name), encoding="utf-8").read()

    v = before
    # 去 IIFE 外壳（独立重做一遍）
    v = re.sub(r"^\s*\(function \(\) \{\s*$", "", v, count=1, flags=re.M)
    v = re.sub(r"^\s*\}\)\(\);\s*$", "", v, count=1, flags=re.M)
    v = re.sub(r"^\s*['\"]use strict['\"];\s*$", "", v, count=1, flags=re.M)
    for d in sp["drops"]:
        assert d in v, "%s：varfix 里没有 %s" % (name, d)
        v = v.replace(d, "", 1)
    for old, new in sp["fixes"]:
        assert old in v, "%s：varfix 里没有 %s" % (name, old[:30])
        v = v.replace(old, new, 1)

    nv, na = norm(v), norm(after)

    print("=" * 88)
    print("%s" % name)
    print("=" * 88)
    print("  改造前 %d 字节 / 改造后 %d 字节（归一化后 %d vs %d 字符）"
          % (len(before.encode()), len(after.encode()), len(nv), len(na)))
    if nv == na:
        print("  ★ 归一化后逐字相同 —— 改造无损")
    else:
        ok_all = False
        lo = 0
        while lo < min(len(nv), len(na)) and nv[lo] == na[lo]:
            lo += 1
        print("  ✗ 有差异，首个不同在第 %d 字符：" % lo)
        print("     前：...%s..." % nv[max(0, lo - 60):lo + 90])
        print("     后：...%s..." % na[max(0, lo - 60):lo + 90])

    # 函数清单必须完全一致。
    # 注意要允许行首空白：改造前的函数体是缩进 2 空格的，用 ^function 会一个都匹配不到，
    # 于是 set(空) <= set(任意) 恒真 —— 检查会**空转**通过（我第一版就是这样）。
    fb = sorted(set(re.findall(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)",
                               strip_comments(before), re.M)))
    fa = sorted(set(re.findall(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([\w$]+)",
                               strip_comments(after), re.M)))
    same_fns = set(fb) == set(fa)
    print("  函数 %d 个；改造前后完全一致：%s%s"
          % (len(fb), "是" if same_fns else "否 ✗",
             "" if same_fns else "  多出 %s / 少了 %s" % (set(fa) - set(fb), set(fb) - set(fa))))
    if not same_fns or not fb:
        ok_all = False
    print()

# 消费方检查
print("=" * 88)
print("消费方（views.js / 两个宿主页）")
print("=" * 88)
views = io.open(r"_中间产物/重构工作区/frontend/js/views.js", encoding="utf-8").read()
checks = [
    ("views.js 用动态 import 加载 gen_ui", "import('/gen/static/gen_ui.js')" in views),
    ("views.js 用动态 import 加载 audit_ui", "import('/audit/static/audit_ui.js')" in views),
    ("views.js 不再动态插 script 标签", "createElement('script')" not in views),
    ("views.js 缓存已加载的模块（不重复请求）", "genLoading = genLoading ||" in views and "auditLoading = auditLoading ||" in views),
]
for label, ok in checks:
    print("  %s %s" % ("√" if ok else "✗", label))
    if not ok:
        ok_all = False

gen_html = io.open(r"_中间产物/重构工作区/frontend/gen.html", encoding="utf-8").read()
audit_html = io.open(r"_中间产物/重构工作区/frontend/audit.html", encoding="utf-8").read()
for label, ok in [
    ("gen.html 用 type=module 加载", 'type="module"' in gen_html and "/gen/static/gen_ui.js" in gen_html),
    ("gen.html 无内联脚本", len(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>[^<]", gen_html)) == 0),
    ("audit.html 用 type=module 加载", 'type="module"' in audit_html and "/audit/static/audit_page.js" in audit_html),
    ("audit.html 无内联 style/script", len(re.findall(r"<(?:style|script)(?![^>]*\bsrc=)[^>]*>[^<]", audit_html)) == 0),
    ("audit.html 引用了外置外壳 CSS", "/audit/static/audit_page.css" in audit_html),
]:
    print("  %s %s" % ("√" if ok else "✗", label))
    if not ok:
        ok_all = False

print()
print("=" * 88)
print("结论：%s" % ("★ 阶段 3 等价性通过" if ok_all else "✗ 有问题待查"))
print("=" * 88)
sys.exit(0 if ok_all else 1)
