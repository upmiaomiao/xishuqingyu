#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""锚点诊断：对某份文档，逐槽位报告"最长能匹配上的锚点长度"，判定失败模式。

· 能匹配到 20+ 字符 → 真锚点，只是我的取法太长 → 缩短即可修
· 最长只匹配到 6~10 字符 → md 与 PDF 用词/语序不同（MinerU 改写） → 难以机械对齐
· 完全匹配不上 → 该处 md 文本在 PDF 里不存在

用法：诊断锚点.py <relpath> [槽位数]
"""
import json
import os
import re
import sys

sys.path.insert(0, "/tmp")
from importlib import import_module

m = import_module("语料正文回填")
BUNDLE = "/data/fagui_rag/okf_bundles"


def longest_match(needle, hay, tail, cursor=0):
    """返回 (最长匹配长度, 位置)。tail=True 用 needle 的后缀去匹配。"""
    for L in range(min(60, len(needle)), 5, -1):
        frag = needle[-L:] if tail else needle[:L]
        p = hay.find(frag, cursor)
        if p >= 0:
            return L, p
    return 0, -1


def main():
    # 用清单序号选文档，避免含空格路径在 shell 里被拆开
    idx = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 6
    targets = json.load(open("/tmp/回填清单.json", encoding="utf-8"))
    targets.sort(key=lambda t: -t["gap"])
    rel = targets[idx]["rel"]
    print(f"[{idx}] 缺口 {targets[idx]['gap']:,} 字  {rel}")
    md_path = os.path.join(BUNDLE, rel)
    text = open(md_path, encoding="utf-8", errors="replace").read()
    pdf = m.locate_pdf(md_path, BUNDLE, "/data/fagui_pdf")
    raw, sk, idx, pages = m.load_pdf_text(pdf)
    md_sk, _ = m.skel_map(text)
    print(f"md 骨架 {len(md_sk):,}  pdf 骨架 {len(sk):,}  PDF {os.path.basename(pdf)[:50]}")

    refs = list(m.IMG_RE.finditer(text))
    slots = []
    for r in refs:
        if slots:
            prev = slots[-1]
            between = text[prev[1]:r.start()]
            if len(m.skel_map(between)[0]) < m.CLUSTER_GAP:
                prev[1] = r.end()
                continue
        slots.append([r.start(), r.end()])
    print(f"槽位（簇）{len(slots)} 个；下面看前 {n} 个\n")

    shown = 0
    for start, end in slots:
        before = m.anchors(m.IMG_RE.sub("", text[:start]), tail=True)
        after = m.anchors(m.IMG_RE.sub("", text[end:]), tail=False)
        if not before:
            print(f"[槽 {shown+1}] 前文骨架不足 12 字符（全是公式/表格记号），无法锚定")
            print(f"        原文前 100 字: {' '.join(text[max(0,start-100):start].split())[-90:]!r}")
            shown += 1
            if shown >= n:
                break
            continue
        Lb, pb = longest_match(before[0], sk, tail=True)
        La, pa = longest_match(after[0], sk, tail=False, cursor=pb if pb >= 0 else 0)
        print(f"[槽 {shown+1}] 前锚最长匹配 {Lb:2d} 字符  后锚最长匹配 {La:2d} 字符")
        print(f"        前文尾部: {' '.join(text[max(0,start-90):start].split())[-80:]!r}")
        print(f"        后文头部: {' '.join(text[end:end+90].split())[:80]!r}")
        shown += 1
        if shown >= n:
            break


if __name__ == "__main__":
    main()
