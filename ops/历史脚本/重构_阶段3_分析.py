#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3 前置分析：gen_ui.js / audit_ui.js 的结构与风格违规。"""
from __future__ import annotations

import io
import re

FILES = {
    "gen_ui.js": r"_中间产物/重构工作区/xishu_pipeline/static/gen_ui.js",
    "audit_ui.js": r"_中间产物/重构工作区/xishu_pipeline/static/audit_ui.js",
}

CLOSE = re.compile(r"^[}\])]")

for name, p in FILES.items():
    src = io.open(p, encoding="utf-8").read()
    lines = src.split("\n")
    print("=" * 90)
    print("%s：%d 行，%d 字节，最长行 %d 字符" % (name, len(lines), len(src.encode()),
                                                 max(len(l) for l in lines)))
    print("=" * 90)

    # 顶层条目
    starts = [i for i, l in enumerate(lines) if l and not l[0].isspace() and not CLOSE.match(l)]
    print("  顶层条目 %d 个：" % len(starts))
    for k, s in enumerate(starts):
        e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(lines) - 1
        first = lines[s]
        m = re.match(r"(?:window\.)?([\w$.]+)\s*=", first)
        mf = re.match(r"(?:async\s+)?function\s+([\w$]+)", first)
        if mf:
            label = "function %s" % mf.group(1)
        elif m:
            label = "赋值 %s" % m.group(1)
        else:
            label = " ".join(first.split())[:50]
        print("    %-9s %4d 行  %s" % ("%d-%d" % (s + 1, e + 1), e - s + 1, label))

    # 风格违规
    var_n = len(re.findall(r"(?<![.\w$])var\s+[\w$]", src))
    eq_n = len(re.findall(r"[^=!<>]==[^=]", src))
    ne_n = len(re.findall(r"[^=!<>]!=[^=]", src))
    print()
    print("  风格违规：var %d 处，== %d 处，!= %d 处" % (var_n, eq_n, ne_n))
    if var_n:
        for m in list(re.finditer(r"(?<![.\w$])var\s+([\w$]+)", src))[:8]:
            ln = src[:m.start()].count("\n") + 1
            print("      var %-22s 行 %d" % (m.group(1), ln))
    if eq_n or ne_n:
        for m in list(re.finditer(r"[^=!<>](==|!=)[^=]", src))[:8]:
            ln = src[:m.start()].count("\n") + 1
            seg = lines[ln - 1].strip()
            print("      %-4s 行 %-4d %s" % (m.group(1), ln, seg[:80]))

    # 模块化相关
    print()
    print("  已有 export：%s" % (re.findall(r"^export\s+.*", src, re.M) or "无"))
    print("  挂到 window 的：%s" % (sorted(set(re.findall(r"window\.([\w$]+)\s*=", src))) or "无"))
    print("  import 语句：%s" % (re.findall(r"^import\s.*", src, re.M) or "无"))
    print("  IIFE 包裹：%s" % ("有" if re.search(r"^\s*\(function\s*\(", src, re.M) else "无"))
    print("  'use strict'：%s" % ("有" if "use strict" in src else "无"))
    print()
