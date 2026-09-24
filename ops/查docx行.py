#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在生成的 docx 里按关键词找行（核对"措施名有没有事实出处"用）。"""
import re
import sys
import zipfile

KWS = sys.argv[2:] or ["布袋", "脱硫", "活性炭", "除尘", "隔声"]


def lines(path):
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    xml = re.sub(r"</w:tc>", " | ", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    return [x.strip() for x in txt.split("\n") if x.strip()]


for p in sys.argv[1:2]:
    ls = lines(p)
    print("文件：%s（%d 段）" % (p, len(ls)))
    for kw in KWS:
        print("\n== 含「%s」的行：" % kw)
        for x in ls:
            if kw in x:
                print("   %s" % x[:190])
