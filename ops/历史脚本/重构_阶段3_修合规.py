#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3 收尾：把 audit_page.css 的 ID 选择器与无前缀类名改成合规写法。

Google CSS 风格指南两条：
  · Avoid ID selectors —— "Class selectors should be preferred in all situations"；
  · Prefixes as namespaces —— 用短而唯一的前缀加连字符。
所以 #auditRoot -> .au-page-root，.sub -> .au-sub，.embed -> .au-embed。
id 本身保留（audit_page.js 要用 getElementById 取容器）。
"""
from __future__ import annotations

import hashlib
import io
import re

FE = r"_中间产物/重构工作区/frontend"
ST = r"_中间产物/重构工作区/xishu_pipeline/static"


def md5(s: str) -> str:
    return hashlib.md5(s.encode()).hexdigest()


# ---------------------------------------------------------------- audit_page.css
p = ST + "/audit_page.css"
src = io.open(p, encoding="utf-8").read()
after = src
subs = [
    ("#auditRoot{", ".au-page-root{"),
    ("header .sub{", "header .au-sub{"),
    ("body.embed header{", "body.au-embed header{"),
]
for old, new in subs:
    assert after.count(old) == 1, "audit_page.css：找不到 `%s`（%d 处）" % (old, after.count(old))
    after = after.replace(old, new, 1)
# 注意：注释里也提到了 body.embed header，所以不能拿 ".embed " 做断言 ——
# 那会把散文当成规则（我这个坑今天已经踩了三次）。
assert "#auditRoot" not in after, "还有 #auditRoot"
assert "header .sub{" not in after, "还有 header .sub{"
assert "body.embed header{" not in after, "还有 body.embed header{"
# 注释里的旧写法同步更新
after = after.replace("（比如 body.embed header）", "（比如 body.au-embed header）", 1)
# 头部注释补一句说明
after = after.replace(
    " * 起因：audit.html 有内联样式、gen.html 没有 —— 同一类页面两种做法。\n",
    " * 起因：audit.html 有内联样式、gen.html 没有 —— 同一类页面两种做法。\n"
    " *\n"
    " * 选择器：一律用 .au- 前缀的类，不用 ID（Google「Avoid ID selectors」）。\n"
    " *   容器 id 仍保留，因为 audit_page.js 要用 getElementById 取它。\n", 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(after)
print("audit_page.css  %d -> %d 字节   md5 %s -> %s"
      % (len(src.encode()), len(after.encode()), md5(src)[:12], md5(after)[:12]))
print("   #auditRoot -> .au-page-root；.sub -> .au-sub；.embed -> .au-embed")
print("   剩余 ID 选择器：%d 个" % len(re.findall(r"#[A-Za-z][\w-]*\s*[{,]", after)))

# ---------------------------------------------------------------- audit.html
p = FE + "/audit.html"
src = io.open(p, encoding="utf-8").read()
after = src
subs = [
    ('<span class="sub">', '<span class="au-sub">'),
    ('<div id="auditRoot"></div>', '<div id="auditRoot" class="au-page-root"></div>'),
]
for old, new in subs:
    assert after.count(old) == 1, "audit.html：找不到 `%s`（%d 处）" % (old, after.count(old))
    after = after.replace(old, new, 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(after)
print("audit.html      %d -> %d 字节   md5 %s -> %s"
      % (len(src.encode()), len(after.encode()), md5(src)[:12], md5(after)[:12]))

# ---------------------------------------------------------------- audit_page.js
p = ST + "/audit_page.js"
src = io.open(p, encoding="utf-8").read()
old = "document.body.classList.add('embed')"
assert src.count(old) == 1
after = src.replace(old, "document.body.classList.add('au-embed')", 1)
io.open(p, "w", encoding="utf-8", newline="\n").write(after)
print("audit_page.js   %d -> %d 字节   md5 %s -> %s"
      % (len(src.encode()), len(after.encode()), md5(src)[:12], md5(after)[:12]))

# ---------------------------------------------------------------- 一致性核对
print()
print("一致性核对（三处命名必须同步）：")
css = io.open(ST + "/audit_page.css", encoding="utf-8").read()
htm = io.open(FE + "/audit.html", encoding="utf-8").read()
js = io.open(ST + "/audit_page.js", encoding="utf-8").read()
for label, ok in [
    ("CSS 定义 .au-page-root", ".au-page-root{" in css),
    ("HTML 用了 class=\"au-page-root\"", 'class="au-page-root"' in htm),
    ("HTML 保留了 id=\"auditRoot\"（JS 要取）", 'id="auditRoot"' in htm),
    ("CSS 定义 header .au-sub", "header .au-sub{" in css),
    ("HTML 用了 class=\"au-sub\"", 'class="au-sub"' in htm),
    ("CSS 定义 body.au-embed", "body.au-embed header{" in css),
    ("JS 加的是 au-embed", "classList.add('au-embed')" in js),
]:
    print("  %s %s" % ("√" if ok else "✗", label))
