#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化 md 语料相对源 PDF 丢失了多少正文。

对每个 md：取其同目录同名 PDF 的文本层字数，与 md 正文字数比较。
重点关注 md 明显短于 PDF 的文档 —— 差额就是"被转成图片又丢失"的内容。
"""
import os
import re
import sys
from collections import Counter

import fitz

IMG_RE = re.compile(r"!\[\]\(images/[0-9A-Za-z]+\.(?:jpg|jpeg|png)\)")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else r"D:\项目\中节能\0911训练"
    corpora = (sys.argv[2] if len(sys.argv) > 2 else
               "生态环境标准规范,生态环境法律法规,生态环境监管执法").split(",")

    docs = []
    for corp in corpora:
        for dp, _dn, fn in os.walk(os.path.join(root, corp)):
            for f in fn:
                if f.endswith(".md"):
                    docs.append(os.path.join(dp, f))

    tot_md = tot_pdf = 0
    no_pdf = 0
    scanned = 0
    lossy = []
    img_ref_docs = 0
    for p in docs:
        d = os.path.dirname(p)
        base = os.path.splitext(os.path.basename(p))[0]
        sib = [x for x in os.listdir(d)
               if x.lower().endswith(".pdf") and os.path.splitext(x)[0] == base]
        md = open(p, encoding="utf-8").read()
        n_md = len(md)
        tot_md += n_md
        if IMG_RE.search(md):
            img_ref_docs += 1
        if not sib:
            no_pdf += 1
            continue
        try:
            doc = fitz.open(os.path.join(d, sib[0]))
            ptxt = "".join(doc[i].get_text() for i in range(doc.page_count))
            doc.close()
        except Exception:
            continue
        n_pdf = len(ptxt)
        if n_pdf < 200:
            scanned += 1
        tot_pdf += n_pdf
        if n_pdf > n_md * 1.5 and n_pdf - n_md > 1500:
            lossy.append((n_pdf - n_md, n_md, n_pdf, os.path.basename(p)[:52]))

    print(f"文档总数 {len(docs)}  (含表格死链 {img_ref_docs})")
    print(f"md 总字数     {tot_md:,}")
    print(f"PDF 文本总字数 {tot_pdf:,}")
    print(f"差额          {tot_pdf - tot_md:,}  ({(tot_pdf-tot_md)/max(tot_md,1)*100:.0f}%)")
    print(f"无同目录 PDF {no_pdf}   PDF 文本层几乎为空(疑似扫描件) {scanned}")
    print(f"\nmd 明显短于 PDF 的文档: {len(lossy)} 份")
    lossy.sort(reverse=True)
    print("丢失最多的 18 份:")
    for diff, n_md, n_pdf, name in lossy[:18]:
        print(f"  少 {diff:7,d} 字   md {n_md:7,d} / pdf {n_pdf:7,d}   {name}")


if __name__ == "__main__":
    main()
