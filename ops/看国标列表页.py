#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印标准列表页里 GB 3095-2026 那段 HTML，看链接/hcno 是怎么写的（只读）。"""
from __future__ import annotations

import re
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")
url = ("https://openstd.samr.gov.cn/bzgk/gb/std_list?p.p1=0&p.p90=circulation_date"
       "&p.p91=desc&p.p2=" + urllib.parse.quote(sys.argv[1] if len(sys.argv) > 1 else "GB 3095"))
req = urllib.request.Request(url, headers={"User-Agent": UA})
html = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
print("页面 %d 字节" % len(html))
for m in re.finditer(r"GB 3095-2026", html):
    s = max(0, m.start() - 700)
    seg = html[s:m.end() + 700]
    seg = re.sub(r"[ \t]+", " ", seg)
    print("=" * 90)
    print(seg)
    break
print("=" * 90)
print("页面里所有 onclick / hcno / showInfo 片段：")
for pat in (r"hcno=[0-9A-Za-z]+", r"onclick=\"[^\"]{0,120}", r"showInfo\([^)]{0,60}\)"):
    hits = re.findall(pat, html)
    print("  %-28s → %s" % (pat, hits[:6] if hits else "（无）"))
