#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在生态环境部「环评导则」栏目里检索某标准的详情页链接。

用法：python 找标准详情页.py 环境风险 [关键词2 ...]
栏目：https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/  (含 index_N.shtml 分页)
"""
import re
import sys
import urllib.parse
import urllib.request

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
BASE = "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/"


def get(url, timeout=40):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decode(raw):
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace")


def main():
    kws = sys.argv[1:] or ["环境风险"]
    pages = [BASE] + [urllib.parse.urljoin(BASE, f"index_{i}.shtml") for i in range(1, 6)]
    seen = set()
    total = 0
    for p in pages:
        try:
            html = decode(get(p))
        except Exception as e:
            print(f"[跳过] {p} {e.__class__.__name__}")
            continue
        found = 0
        for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{2,80}?)\s*</a>', html):
            href, text = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            if not text or href.startswith(("http", "javascript", "#")):
                continue
            if not any(k in text for k in kws):
                continue
            url = urllib.parse.urljoin(p, href)
            if url in seen:
                continue
            seen.add(url)
            found += 1
            total += 1
            print(f"  {text}\n    {url}")
        print(f"[{p}] 命中 {found}")
    print(f"合计 {total}")


if __name__ == "__main__":
    main()