#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""代码结构体检：前端是不是组件式/分离的？还是一个大文件塞所有 CSS？

实测三类东西：
  1. 前端目录里有哪些文件、多大
  2. index.html 内部结构：内联 <style>/<script> 各几个、内联 CSS/JS 多少字节、最长行多长
  3. 后端包是不是拆开的、每个模块多少行
"""
from __future__ import annotations

import os
import re

ROOT = "/home/test/xishu_qingyu_serve"
FRONT = os.path.join(ROOT, "frontend")
STATIC = os.path.join(ROOT, "xishu_pipeline", "static")
PKG = os.path.join(ROOT, "xishu_pipeline")


def human(n: int) -> str:
    return "%.1f KB" % (n / 1024.0) if n >= 1024 else "%d B" % n


def walk(d: str, title: str) -> None:
    print("=" * 76)
    print(title)
    print("=" * 76)
    if not os.path.isdir(d):
        print("  （目录不存在）")
        return
    for dirpath, _dirs, files in os.walk(d):
        rel = os.path.relpath(dirpath, d)
        for f in sorted(files):
            if f.endswith((".pyc",)):
                continue
            p = os.path.join(dirpath, f)
            n = os.path.getsize(p)
            try:
                lines = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
            except Exception:
                lines = -1
            print("  %-42s %9s  %5d 行" % (os.path.join(rel, f) if rel != "." else f, human(n), lines))
    print()


walk(FRONT, "① frontend/ 目录（问答主页所在）")
walk(STATIC, "② xishu_pipeline/static/ 目录（各视图的静态资源）")

print("=" * 76)
print("③ index.html 内部结构 —— 内联了多少东西")
print("=" * 76)
html = open(os.path.join(FRONT, "index.html"), encoding="utf-8").read()
total = len(html.encode("utf-8"))
styles = re.findall(r"<style[^>]*>(.*?)</style>", html, re.S)
scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.S)
print("  文件总大小          %s" % human(total))
print("  行数                %d" % (html.count("\n") + 1))
print("  <style> 块数        %d，合计 %s（占 %.0f%%）"
      % (len(styles), human(sum(len(s.encode()) for s in styles)),
         100.0 * sum(len(s.encode()) for s in styles) / total))
print("  <script> 块数       %d，合计 %s（占 %.0f%%）"
      % (len(scripts), human(sum(len(s.encode()) for s in scripts)),
         100.0 * sum(len(s.encode()) for s in scripts) / total))
print("  外部 css/js 引用    %d 个" % len(re.findall(r'<(?:link|script)[^>]+(?:href|src)=', html)))
print()
lines = html.split("\n")
lens = sorted(((len(l), i + 1) for i, l in enumerate(lines)), reverse=True)
print("  最长的 5 行（说明是不是被压成超长行）：")
for ln, idx in lens[:5]:
    print("    第 %3d 行  %6d 字符" % (idx, ln))
print("  >1000 字符的行数    %d" % sum(1 for l in lines if len(l) > 1000))

print()
print("=" * 76)
print("④ 后端 xishu_pipeline/ 是不是拆开的")
print("=" * 76)
rows = []
for f in sorted(os.listdir(PKG)):
    if f.endswith(".py") and not f.endswith(".pyc"):
        p = os.path.join(PKG, f)
        n = sum(1 for _ in open(p, encoding="utf-8", errors="replace"))
        rows.append((n, f, os.path.getsize(p)))
rows.sort(reverse=True)
for n, f, b in rows:
    print("  %-22s %5d 行  %9s" % (f, n, human(b)))
print("  ---")
print("  模块数 %d，合计 %d 行" % (len(rows), sum(r[0] for r in rows)))
print("  最大模块：%s（%d 行）" % (rows[0][1], rows[0][0]))
