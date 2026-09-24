#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从生态环境部官网下载标准文本 PDF（通用版，按详情页 URL）。

用法：python 下载标准文本.py [--out 目录]
产出：<out>/<标准号去空格>.pdf，并打印页数/字数/标准号是否出现。
"""
import os
import re
import sys
import urllib.parse
import urllib.request

import fitz

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "判据库", "标准文本")

# (标准号, 名称, 详情页 URL)
TARGETS = [
    ("HJ 169-2018", "建设项目环境风险评价技术导则",
     "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/201810/t20181024_665360.shtml"),
]


def get(url, timeout=60):
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


def pdf_links(html, page_url):
    out = []
    for m in re.finditer(r'(?:href|src)=["\']([^"\']+?(?:\.pdf|\.PDF|W020\d+[^"\']*))["\']', html):
        out.append(urllib.parse.urljoin(page_url, m.group(1)))
    for m in re.finditer(r'["\'](\.?/?[^"\']*?W020\d{8,}\d*[^"\']*?)["\']', html):
        out.append(urllib.parse.urljoin(page_url, m.group(1)))
    seen, uniq = set(), []
    for u in out:
        if u not in seen and u.lower().endswith(".pdf"):
            seen.add(u)
            uniq.append(u)
    return uniq


def main():
    out = OUT
    if "--out" in sys.argv:
        out = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(out, exist_ok=True)
    for sid, name, page in TARGETS:
        print(f"\n===== {sid} {name}")
        html = decode(get(page))
        cand = pdf_links(html, page)
        print(f"  详情页 {page}")
        print(f"  候选 PDF {len(cand)} 个")
        if not cand:
            print("  [无 PDF 链接]")
            continue
        dest = os.path.join(out, sid.replace(" ", "_") + ".pdf")
        for u in cand:
            try:
                raw = get(u, timeout=120)
            except Exception as e:
                print(f"  下载失败 {u[:70]}: {e.__class__.__name__}")
                continue
            if not raw.startswith(b"%PDF"):
                continue
            open(dest, "wb").write(raw)
            d = fitz.open(dest)
            txt = "".join(d[i].get_text() for i in range(d.page_count))
            pages = d.page_count
            d.close()
            flat = txt.replace(" ", "").replace("\u2014", "-")
            print(f"  ✓ {os.path.basename(dest)}  {pages} 页  {len(txt):,} 字  "
                  f"标准号出现={sid.replace(' ', '') in flat}")
            print(f"    来源 {u[:80]}")
            print(f"    摘录 {' '.join(txt.split())[:120]}")
            break


if __name__ == "__main__":
    sys.exit(main())