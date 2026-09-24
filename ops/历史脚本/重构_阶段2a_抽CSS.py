#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2a：把 index.html 的两个内联 <style> 抽成 frontend/app.css（并美化）。

无损保证：美化只动空白，所以「去掉所有空白后的字符串」必须与原文逐字符相同。
这个断言是硬门槛，不通过就不写文件。
"""
from __future__ import annotations

import io
import re
import sys

SRC = r"_中间产物/重构工作区/frontend/index.html"
DST_CSS = r"_中间产物/重构工作区/frontend/app.css"
DST_HTML = r"_中间产物/重构工作区/frontend/index.html.新"


def norm(s: str) -> str:
    """去掉全部空白，用于证明美化是无损的。"""
    return re.sub(r"\s+", "", s)


def beautify(css: str) -> str:
    """极简 CSS 美化器：只重排空白，不改任何 token。"""
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    i, n = 0, len(css)
    while i < n:
        c = css[i]
        if c == "/" and i + 1 < n and css[i + 1] == "*":
            j = css.find("*/", i + 2)
            j = n - 2 if j < 0 else j
            comment = css[i:j + 2]
            if not "".join(buf).strip():
                out.append("  " * depth + comment)
            else:
                buf.append(comment)
            i = j + 2
            continue
        if c == "{":
            out.append("  " * depth + " ".join("".join(buf).split()) + " {")
            buf = []
            depth += 1
            i += 1
            continue
        if c == "}":
            decl = "".join(buf).strip()
            if decl:
                out.append("  " * depth + decl)
            buf = []
            depth -= 1
            out.append("  " * depth + "}")
            i += 1
            continue
        if c == ";" and depth > 0:
            decl = "".join(buf).strip()
            if decl:
                out.append("  " * depth + decl + ";")
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return "\n".join(out) + "\n"


html = io.open(SRC, encoding="utf-8").read()
blocks = list(re.finditer(r"<style[^>]*>(.*?)</style>", html, re.S))
assert len(blocks) == 2, "预期 2 个 style 块，实际 %d" % len(blocks)

css1 = blocks[0].group(1)
css2 = blocks[1].group(1)
raw = css1 + "\n" + css2

print("=" * 74)
print("① 抽取前体检")
print("=" * 74)
print("  块1 %d 字节 / 块2 %d 字节 / 合计 %d 字节"
      % (len(css1.encode()), len(css2.encode()), len(raw.encode())))
print("  url( 出现次数：%d（data URI 里的 ; 会干扰美化器）" % raw.count("url("))
print("  大括号：{ %d 个 / } %d 个" % (raw.count("{"), raw.count("}")))
assert raw.count("{") == raw.count("}"), "原文大括号就不平衡"
for kw in ("url(data:", "url(\"data:", "url('data:"):
    assert kw not in raw, "含 data URI，需要更谨慎的美化器：%s" % kw

print()
print("=" * 74)
print("② 美化 + 无损校验")
print("=" * 74)
pretty = beautify(raw)
if norm(pretty) != norm(raw):
    print("  ✗ 去空白后不一致 —— 美化有损，拒绝写入")
    a, b = norm(raw), norm(pretty)
    for k in range(min(len(a), len(b))):
        if a[k] != b[k]:
            print("    首个差异在第 %d 字符：" % k)
            print("      原：%r" % a[max(0, k - 40):k + 40])
            print("      新：%r" % b[max(0, k - 40):k + 40])
            break
    print("    长度 原 %d / 新 %d" % (len(a), len(b)))
    sys.exit(1)
print("  ★ 去空白后逐字符一致 —— 美化无损")
print("  原文 %d 行 -> 美化后 %d 行" % (raw.count("\n") + 1, pretty.count("\n") + 1))
print("  最长行：原 %d 字符 -> 新 %d 字符"
      % (max(len(l) for l in raw.split("\n")), max(len(l) for l in pretty.split("\n"))))

header = """/* 悉数清宇 · 问答主页样式表
 *
 * 2026-09-18 从 frontend/index.html 的两个内联 <style> 抽出（阶段 2a）。
 * 抽取原因：Google HTML/CSS Style Guide「Separation of Concerns」——
 *   "Strictly keep structure (markup), presentation (styling), and behavior (scripting) apart"
 * 抽取前内联 CSS 占 index.html 全文 32%，且被压成最长 2497 字符的行，无法评审。
 *
 * 内容来源（按原顺序，未改动任何 token，仅重排空白）：
 *   原第 1 个 <style>（141 条规则，12843 字节）：页面骨架 / 侧栏 / 消息 / 引用卡 / 知识图谱 / 响应式
 *   原第 2 个 <style>（5 条规则，284 字节）：报告审核与报告编制两个挂载容器的布局
 *
 * 变量声明在 :root 上，改配色只改这一处。
 */

"""
css_out = header + pretty
io.open(DST_CSS, "w", encoding="utf-8", newline="\n").write(css_out)
print()
print("  已写 %s（%d 字节，%d 行）" % (DST_CSS, len(css_out.encode()), css_out.count("\n") + 1))

# ---- 改 HTML：两个 style 块 -> 一个 <link> ----
print()
print("=" * 74)
print("③ 改 HTML：删两个 <style>，<head> 里加一个 <link>")
print("=" * 74)
new_html = html
# 先删第 2 块（在 body 里），再删第 1 块，避免位移
new_html = new_html[:blocks[1].start()] + new_html[blocks[1].end():]
new_html = new_html[:blocks[0].start()] + new_html[blocks[0].end():]

anchor = '<title>悉数清宇大模型</title>'
assert anchor in new_html, "找不到 title 锚点"
new_html = new_html.replace(
    anchor,
    anchor + '\n<link rel="stylesheet" href="/static/app.css">', 1)

# 原第 7 行是 "<style>…</style></head><body><div class=\"app\">"，删掉 style 后
# 会变成 "</head><body>…"，补回换行便于阅读
new_html = new_html.replace("</head><body>", "</head>\n<body>", 1)

assert "<style" not in new_html, "还有残留 style 块"
assert '<link rel="stylesheet" href="/static/app.css">' in new_html
io.open(DST_HTML, "w", encoding="utf-8", newline="\n").write(new_html)
print("  已写 %s（%d 字节，%d 行）" % (DST_HTML, len(new_html.encode()), new_html.count("\n") + 1))

print()
print("=" * 74)
print("④ 结构不变量校验")
print("=" * 74)
ids_old = sorted(re.findall(r'id="([^"]+)"', html))
ids_new = sorted(re.findall(r'id="([^"]+)"', new_html))
print("  HTML id 数量：原 %d -> 新 %d  %s" % (len(ids_old), len(ids_new), "√" if ids_old == ids_new else "✗"))
js_old = re.search(r"<script[^>]*>(.*?)</script>", html, re.S).group(1)
js_new = re.search(r"<script[^>]*>(.*?)</script>", new_html, re.S).group(1)
print("  <script> 内容完全未动：%s" % ("√" if js_old == js_new else "✗"))
print("  原文件字节：%d -> 新 %d（减少 %d，%.0f%%）"
      % (len(html.encode()), len(new_html.encode()),
         len(html.encode()) - len(new_html.encode()),
         100.0 * (len(html.encode()) - len(new_html.encode())) / len(html.encode())))
print("  新 index.html 最长行：%d 字符" % max(len(l) for l in new_html.split("\n")))
