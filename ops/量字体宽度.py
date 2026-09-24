# -*- coding: utf-8 -*-
"""量一下：china-s 的 text_length 与实际渲染宽度差多少。

背景：汇总页的文字按 text_length 折行，结果数字/英文多的行实际比量出来的宽，
直接把字顶出页面、压到隔壁列。这里逐类字符对比"量出来的"与"渲出来的"。
"""
import pymupdf

CASES = [
    ("纯中文", "审核意见汇总说明文字"),
    ("纯数字", "1234567890"),
    ("数字带P", "P177、P1770"),
    ("英文", "HJ/T169-2018"),
    ("混合", "报告列 12 项，其中 6 项可在 HJ 169 表B.1 对应"),
    ("全角括号", "（版面框出 6）"),
    ("表意空格", "甲　乙　丙"),
    ("ASCII空格", "A B C D"),
    ("下划线", "__________"),
    ("标点", "、；：，。—…"),
]

doc = pymupdf.open()
page = doc.new_page(width=2000, height=400)
font = pymupdf.Font("china-s")
y = 40
for name, s in CASES:
    size = 9.5
    measured = font.text_length(s, fontsize=size)
    page.insert_text((30, y), s, fontname="china-s", fontsize=size)
    y += 30
print("%-10s %8s %8s %7s  %s" % ("样本", "量出", "实际", "倍率", "文字"))
for name, s in CASES:
    size = 9.5
    measured = font.text_length(s, fontsize=size)
    # 只取刚画的那一行：按 baseline 找
    found = None
    for blk in page.get_text("dict")["blocks"]:
        for ln in blk.get("lines", []):
            for sp in ln["spans"]:
                if sp["text"].strip() == s.strip():
                    found = sp["bbox"]
    if not found:
        print("%-10s %8.1f  （没找到）" % (name, measured))
        continue
    real = found[2] - found[0]
    print("%-10s %8.1f %8.1f %6.2fx  %s" % (name, measured, real, real / measured if measured else 0, s[:24]))
doc.close()
