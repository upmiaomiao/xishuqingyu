#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从生态环境部官网抓取环评核心导则的标准文本 PDF（在服务器上跑）。

对每本导则：抓详情页 → 找 PDF 链接 → 下载 → 用 PyMuPDF 校验（页数/正文字数/是否含标准号）。
输出目录默认 /data/fagui_rag/guides_pdf。
"""
import os
import re
import sys
import urllib.parse
import urllib.request

import fitz

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
OUT = os.environ.get("GUIDE_OUT", "/data/fagui_rag/guides_pdf")

GUIDES = [
    ("HJ 2.1-2016", "建设项目环境影响评价技术导则 总纲",
     "/201612/t20161214_369043.shtml"),
    ("HJ 2.2-2018", "环境影响评价技术导则 大气环境",
     "/201808/t20180814_451386.shtml"),
    ("HJ 2.3-2018", "环境影响评价技术导则 地表水环境",
     "/201810/t20181024_665363.shtml"),
    ("HJ 2.4-2021", "环境影响评价技术导则 声环境",
     "/202203/t20220323_972427.shtml"),
    ("HJ 610-2016", "环境影响评价技术导则 地下水环境",
     "/201601/t20160113_326075.shtml"),
    ("HJ 964-2018", "环境影响评价技术导则 土壤环境（试行）",
     "/201809/t20180921_626413.shtml"),
    ("HJ 19-2022", "环境影响评价技术导则 生态影响",
     "/202203/t20220323_972428.shtml"),
    ("HJ 130-2019", "规划环境影响评价技术导则 总纲",
     "/201912/t20191224_749944.shtml"),
]
HOST = "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz"


def get(url: str, timeout: int = 40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def decode(raw: bytes) -> str:
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


def pdf_links(html: str, page_url: str):
    out = []
    for m in re.finditer(r'(?:href|src)="([^"]+?(?:\.pdf|\.PDF|W020\d+[^"]*))"', html):
        out.append(urllib.parse.urljoin(page_url, m.group(1)))
    # 有些页面把附件地址写在脚本字符串里
    for m in re.finditer(r'["\'](\.?/?[^"\']*?W020\d{8}\d+[^"\']*?)["\']', html):
        out.append(urllib.parse.urljoin(page_url, m.group(1)))
    seen, uniq = set(), []
    for u in out:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def main():
    os.makedirs(OUT, exist_ok=True)
    ok = fail = 0
    for sid, name, path in GUIDES:
        page = HOST + path
        print(f"\n===== {sid} {name}")
        try:
            html = decode(get(page))
        except Exception as e:
            print(f"  详情页抓取失败: {e.__class__.__name__}: {e}")
            fail += 1
            continue
        links = pdf_links(html, page)
        cand = [u for u in links if u.lower().endswith(".pdf") or "W020" in u]
        print(f"  详情页 {page}")
        print(f"  候选链接 {len(cand)} 个: {cand[:3]}")
        if not cand:
            # 打印页面里出现 '附件' 附近的片段，便于人工判断
            i = html.find("附件")
            if i > 0:
                print("  附件附近片段:", re.sub(r"\s+", " ", html[i:i + 300]))
            fail += 1
            continue

        dest = os.path.join(OUT, f"{sid.replace(' ', '_')}.pdf")
        got = False
        for u in cand:
            try:
                raw = get(u, timeout=90)
            except Exception as e:
                print(f"  下载失败 {u[:80]}: {e.__class__.__name__}")
                continue
            if not raw.startswith(b"%PDF"):
                print(f"  非 PDF 内容（{len(raw)} 字节）: {u[:80]}")
                continue
            open(dest, "wb").write(raw)
            try:
                d = fitz.open(dest)
                txt = "".join(d[i].get_text() for i in range(d.page_count))
                pages = d.page_count
                d.close()
            except Exception as e:
                print(f"  打开失败: {e}")
                continue
            has = sid.replace(" ", "") in txt.replace(" ", "").replace("\u2014", "-")
            print(f"  ✓ {os.path.basename(dest)}  {pages} 页  {len(txt):,} 字  "
                  f"标准号出现={has}  来源={u[:70]}")
            print(f"    摘录: {' '.join(txt.split())[:150]}")
            got = True
            break
        ok += 1 if got else 0
        fail += 0 if got else 1
    print(f"\n成功 {ok} / 失败 {fail}，输出目录 {OUT}")


if __name__ == "__main__":
    sys.exit(main())
