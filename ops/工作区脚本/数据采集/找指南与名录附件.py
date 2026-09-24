#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找《报告表编制技术指南》与《有毒有害大气污染物名录》的官方附件地址。

方法：抓页面 → 列出所有 docx/pdf/doc 链接 + 打印与"专项评价""有毒有害"相关的正文片段。
"""
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
PAGES = sys.argv[1:] or [
    "https://www.gov.cn/zhengce/zhengceku/2021-01/04/content_5576531.htm",
    "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/201811/t20181113_673567.html",
]


def get(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


for url in PAGES:
    print("=" * 78)
    print(url)
    try:
        html = get(url)
    except Exception as e:
        print(f"  抓取失败: {e.__class__.__name__}: {e}")
        continue
    links = set()
    for m in re.finditer(r'(?:href|src)="([^"]+\.(?:docx|doc|pdf|DOCX|PDF))"', html):
        links.add(urllib.parse.urljoin(url, m.group(1)))
    print(f"  附件链接 {len(links)} 个:")
    for l in sorted(links):
        print("   ", l)
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    for kw in ("专项评价", "有毒有害", "附件", "污染影响类"):
        for m in list(re.finditer(kw, text))[:2]:
            seg = text[max(0, m.start() - 80): m.start() + 160]
            print(f"  [{kw}] …{seg}…")
