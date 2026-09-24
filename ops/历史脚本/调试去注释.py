#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""调试：为什么去注释后长度不一致。"""
import io
import re

P = r"_中间产物/重构工作区/frontend/app.css"
css = io.open(P, encoding="utf-8").read()


def strip_comments(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)


def norm(s):
    return re.sub(r"\s+", "", s)


print("原文长度 %d，去注释后 %d，差 %d"
      % (len(css), len(strip_comments(css)), len(css) - len(strip_comments(css))))
print()
print("=== 原文里 /* 和 */ 的出现位置 ===")
for m in re.finditer(r"/\*|/\*|\*/", css):
    pass
opens = [m.start() for m in re.finditer(r"/\*", css)]
closes = [m.start() for m in re.finditer(r"\*/", css)]
print("  /* 出现 %d 次，位置 %s" % (len(opens), opens[:10]))
print("  */ 出现 %d 次，位置 %s" % (len(closes), closes[:10]))
print()
print("=== 每个 /* 的上下文（前 60 字）===")
for o in opens:
    line = css[:o].count("\n") + 1
    print("  第 %d 行 @%d: %r" % (line, o, css[o:o + 60].replace("\n", "\\n")))
print()
print("=== 去注释后的前 300 字 ===")
print(repr(strip_comments(css)[:300]))
print()
print("=== 原文前 300 字 ===")
print(repr(css[:300]))
