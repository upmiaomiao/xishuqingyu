#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从生态环境部官网找环评导则的标准文本 PDF 链接。

思路：先抓"环境影响评价技术导则"分类目录页，拿到各标准的详情页链接；
详情页里通常有标准文本 PDF 附件（W020xxxxxx.pdf）。

用法：
  python3 找导则PDF.py list                  # 只列目录页找到的条目
  python3 找导则PDF.py pdf <详情页URL> ...    # 对给定详情页解析 PDF 链接
"""
import re
import sys
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
BASES = [
    "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/",
    "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/index_1.shtml",
    "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/index_2.shtml",
]


def get(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def cmd_list():
    seen = set()
    for base in BASES:
        try:
            html = get(base)
        except Exception as e:
            print(f"[跳过] {base}  {e.__class__.__name__}: {e}")
            continue
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>([^<]{6,80})</a>', html):
            href, text = m.group(1), m.group(2).strip()
            if "环境影响评价技术导则" not in text and "环境影响报告" not in text:
                continue
            url = href if href.startswith("http") else "https://www.mee.gov.cn" + href
            if url in seen:
                continue
            seen.add(url)
            print(f"{text}\n    {url}")
    print(f"\n合计 {len(seen)} 条")


def cmd_pdf(urls):
    for url in urls:
        try:
            html = get(url)
        except Exception as e:
            print(f"[失败] {url}  {e}")
            continue
        title = ""
        mt = re.search(r"<title>(.*?)</title>", html, re.S)
        if mt:
            title = mt.group(1).strip()[:60]
        pdfs = set()
        for m in re.finditer(r'href="([^"]+\.(?:pdf|PDF))"', html):
            pdfs.add(m.group(1))
        for m in re.finditer(r'href="([^"]*W020\d+[^"]*)"', html):
            pdfs.add(m.group(1))
        print(f"--- {title}\n    {url}")
        if not pdfs:
            print("    （未找到 pdf 链接）")
        for p in sorted(pdfs):
            full = p if p.startswith("http") else "https://www.mee.gov.cn" + (
                p if p.startswith("/") else "/" + p.lstrip("./"))
            print(f"    PDF: {full}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] == "list":
        cmd_list()
    else:
        cmd_pdf(sys.argv[2:])
