#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探查生态环境部标准详情页里到底装了什么（HTML 正文？iframe？附件区？）。"""
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
URL = sys.argv[1] if len(sys.argv) > 1 else "https://www.mee.gov.cn/201612/t20161214_369043.shtml"

req = urllib.request.Request(URL, headers=UA)
with urllib.request.urlopen(req, timeout=40) as r:
    raw = r.read()
html = raw.decode("utf-8", "replace")
print(f"URL {URL}\n原始字节 {len(raw)}")
print("含 <iframe:", html.count("<iframe"), " 含 <embed:", html.count("<embed"),
      " 含 .pdf:", html.count(".pdf"), " 含 W020:", html.count("W020"))
print("含 '适用范围':", html.count("适用范围"), " 含 '总纲':", html.count("总纲"))

# 去掉脚本样式后看正文长度
body = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
text = re.sub(r"(?s)<[^>]+>", " ", body)
text = re.sub(r"\s+", " ", text)
print(f"\n去标签正文 {len(text)} 字；前 600 字：\n{text[:600]}")

print("\n--- 所有 iframe/embed/object 源 ---")
for m in re.finditer(r'(?i)<(?:iframe|embed|object)[^>]*?(?:src|data)="([^"]+)"', html):
    print("   ", m.group(1))

print("\n--- 含 pdf/W020/附件的 href 与 onclick ---")
for m in re.finditer(r'(?i)(?:href|onclick)="([^"]*(?:pdf|W020|附件|fujian)[^"]*)"', html):
    print("   ", m.group(1)[:160])

print("\n--- 正文里出现'标准文本'附近的片段 ---")
i = html.find("标准文本")
if i > 0:
    print(re.sub(r"\s+", " ", html[max(0, i - 200):i + 400]))
else:
    print("   （未出现'标准文本'）")
