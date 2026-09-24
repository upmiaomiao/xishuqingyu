#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""诊断：HJ 169 表B.1 某些行的「名称」单元格里 span 的坐标与字号。

用途：确认 find_tables 的单元格文本拼接错序（下标被甩到末尾）的成因，
以决定是否改用 span 级重建。
"""
import os
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
PDF = os.path.join(ROOT, "判据库", "标准文本", "HJ_169-2018.pdf")

WANT = {"53", "55", "381"}


def all_spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                out.append(s)
    return out


def inside(span, rect):
    x, y = (span["bbox"][0] + span["bbox"][2]) / 2, (span["bbox"][1] + span["bbox"][3]) / 2
    return rect[0] - 1 <= x <= rect[2] + 1 and rect[1] - 1 <= y <= rect[3] + 1


def main():
    d = fitz.open(PDF)
    for pno in range(16, 26):
        pg = d[pno]
        spans = all_spans(pg)
        for tb in pg.find_tables().tables:
            for row in tb.rows:
                num = "".join(s["text"] for s in spans if inside(s, row.cells[0])).strip()
                if num not in WANT:
                    continue
                print(f"\n===== page {pno} 序号 {num}")
                for ci, rect in enumerate(row.cells):
                    got = [s for s in spans if inside(s, rect)]
                    got.sort(key=lambda s: (round(s["bbox"][1], 1), s["bbox"][0]))
                    print(f"  列{ci} rect={tuple(round(v,1) for v in rect)}")
                    for s in got:
                        print(f"     x={s['bbox'][0]:7.1f} y={s['bbox'][1]:7.1f} "
                              f"size={s['size']:.1f} {s['text']!r}")
                    print(f"     拼接(按y,x) = {''.join(s['text'] for s in got)!r}")


if __name__ == "__main__":
    sys.exit(main())