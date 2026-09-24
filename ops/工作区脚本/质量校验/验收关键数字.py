#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验收测试：回填后，专业问答真正需要的关键内容是否"从无到有"。

判据（机械、可复现）：
  对每个 (文档, 关键串)：原文里**没有**、补后**有** → 通过。
比对走骨架（只认汉字/字母/数字，全角转半角），免疫 PDF 与 md 的排版差异。

用法：验收关键数字.py [stage目录] [bundle目录]
"""
import os
import re
import sys

STAGE = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stage_probe"
BUNDLE = sys.argv[2] if len(sys.argv) > 2 else "/data/fagui_rag/okf_bundles"
FW = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
KEEP = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")


def skel(s):
    return "".join(c for c in (s or "").translate(FW) if KEEP.match(c))


# (文档名关键词, 关键串, 说明)
CASES = [
    ("国家危险废物名录", "841-001-01", "危废代码：判断'是不是危废'的依据"),
    ("国家危险废物名录", "HW01", "危废类别码"),
    ("储油库大气污染物排放标准（GB 20950—2020", "NMHC", "储油库特征污染物"),
    ("制糖工业水污染物排放标准（GB 21909-2008", "悬浮物", "制糖限值项目"),
    ("制糖工业水污染物排放标准（GB 21909-2008", "五日生化需氧量", "制糖限值项目"),
    ("一般工业固体废物贮存和填埋污染控制标准 GB 18599", "渗透系数", "固废场防渗核心指标"),
    ("污染源源强核算技术指南 水泥工业", "氮氧化物", "水泥行业源强核算因子"),
    ("排污许可证申请与核发技术规范 生活垃圾焚烧", "焚烧", "焚烧许可规范"),
]


def find(root, kw):
    out = []
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(".md") and kw in f:
                out.append(os.path.join(dp, f))
    return out


ok = fail = miss_doc = 0
for kw, needle, note in CASES:
    staged = find(STAGE, kw)
    if not staged:
        print(f"[未覆盖] {kw}｜{note}")
        miss_doc += 1
        continue
    n = skel(needle)
    for sp in staged:
        rel = os.path.relpath(sp, STAGE)
        op = os.path.join(BUNDLE, rel)
        if not os.path.isfile(op):
            continue
        old, new = open(op, encoding="utf-8", errors="replace").read(), \
            open(sp, encoding="utf-8", errors="replace").read()
        in_old, in_new = n in skel(old), n in skel(new)
        if in_new and not in_old:
            verdict = "通过（从无到有）"
            ok += 1
        elif in_new and in_old:
            verdict = "原本就有"
            ok += 1
        else:
            verdict = "未通过（补后仍无）"
            fail += 1
        print(f"[{verdict:16s}] {needle:16s} {len(old):7,d}→{len(new):7,d}  "
              f"{os.path.basename(sp)[:44]}")
    print(f"          └ {note}")

print(f"\n通过/原本就有 {ok} 项，未通过 {fail} 项，清单外文档 {miss_doc} 项")
sys.exit(1 if fail else 0)
