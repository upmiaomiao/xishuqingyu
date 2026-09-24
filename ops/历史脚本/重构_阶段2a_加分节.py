#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2a-补（修正版）：给 app.css 加分节横幅 + 目录。

上一版失败原因：横幅写成 `/* ====` 却没写闭合的 `*/`，
于是注释一直吞到文件尾，去注释校验立刻发现长度不符（多出 1575 字符）。
本版每块横幅都严格闭合，并把「去注释后逐字符一致」作为硬门槛。
"""
from __future__ import annotations

import io
import re
import sys

P = r"_中间产物/重构工作区/frontend/app.css"
css = io.open(P, encoding="utf-8").read()

SECTIONS = [
    ("设计变量", ":root"),
    ("基础与重置", "*"),
    ("页面骨架", ".app"),
    ("侧栏与历史", ".sidebar"),
    ("主区与顶栏", ".main"),
    ("消息与欢迎页", ".messages"),
    ("引用卡片与来源", ".cite"),
    ("输入区", ".composer-wrap"),
    ("Markdown 表格", ".md-table-wrap"),
    ("图片上传与预览", ".attach"),
    ("知识图谱", ".kg-view"),
    ("响应式", "@media"),
]


def strip_comments(s: str) -> str:
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


lines = css.split("\n")

# ---- 切出文件头注释 ----
assert lines[0].startswith("/*"), "第一行不是注释开头"
head_end = None
for i, l in enumerate(lines):
    if l.rstrip().endswith("*/"):
        head_end = i
        break
assert head_end is not None, "找不到头注释结束"
head = lines[:head_end + 1]
body = lines[head_end + 1:]
while body and not body[0].strip():
    body.pop(0)
print("头注释 %d 行，正文 %d 行" % (len(head), len(body)))

# ---- 找分节位置 ----
sect_idx: list[tuple[str, int]] = []
for title, anchor in SECTIONS:
    found = None
    for i, l in enumerate(body):
        s = l.strip()
        if s.startswith(anchor) and "{" in s:
            found = i
            break
    if found is None:
        print("  ✗ 找不到分节锚点：%s (%s)" % (title, anchor))
        sys.exit(1)
    sect_idx.append((title, found))
assert sect_idx == sorted(sect_idx, key=lambda x: x[1]), "分节顺序必须递增"

# ---- 插横幅（每块都闭合）----
BANNER = ["", "/* " + "=" * 62, " *  %s", " * " + "=" * 62 + " */", ""]
new_body: list[str] = []
final_line_of: dict[str, int] = {}
added = 0
si = 0
for i, l in enumerate(body):
    if si < len(sect_idx) and sect_idx[si][1] == i:
        title = sect_idx[si][0]
        for b in BANNER:
            new_body.append(b % title if "%s" in b else b)
        added += len(BANNER)
        final_line_of[title] = len(new_body)  # 占位，稍后加头注释行数
        si += 1
    new_body.append(l)

# ---- 组头注释（含目录）----
toc = [" *", " * 目录："]
HEAD_LINES = 20  # 头注释最终行数（下方 assert 会校验）
for title, _i in sect_idx:
    toc.append(" *   %-22s 约第 %d 行" % (title, final_line_of[title] + HEAD_LINES))
toc.append(" */")
new_head = head[:-1] + toc
HEAD_LINES = len(new_head)

out = new_head + new_body
new = "\n".join(out)
if not new.endswith("\n"):
    new += "\n"

print()
print("=" * 74)
print("无损校验（去注释 + 去空白）")
print("=" * 74)
a, b = norm(strip_comments(css)), norm(strip_comments(new))
if a != b:
    print("  ✗ 不一致，拒绝写入")
    k = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    print("    首个差异在第 %d 字符" % k)
    print("      原：%r" % a[max(0, k - 40):k + 40])
    print("      新：%r" % b[max(0, k - 40):k + 40])
    print("    长度 原 %d / 新 %d" % (len(a), len(b)))
    sys.exit(1)
print("  ★ 去注释去空白后逐字符一致 —— 规则一条没动")
n_old = len(re.findall(r"\{", strip_comments(css)))
n_new = len(re.findall(r"\{", strip_comments(new)))
print("  规则块数：%d -> %d  %s" % (n_old, n_new, "√" if n_old == n_new else "✗"))
assert n_old == n_new
# 注释必须成对
print("  注释开合：/* %d 个 / */ %d 个  %s"
      % (new.count("/*"), new.count("*/"), "√" if new.count("/*") == new.count("*/") else "✗"))
assert new.count("/*") == new.count("*/")

io.open(P, "w", encoding="utf-8", newline="\n").write(new)
print()
print("  已写 %s（%d 行，%d 字节）" % (P, new.count("\n") + 1, len(new.encode())))
print("  分节位置：")
for title, _i in sect_idx:
    print("    %-22s 第 %d 行" % (title, final_line_of[title] + HEAD_LINES))
