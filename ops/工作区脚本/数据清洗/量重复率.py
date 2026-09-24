#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化"补录内容里有多少是原文已有的"（重复率）。

补录段落被 APPEND_HEAD / TABLE_HEAD 标记分隔，直接切出来与**原始 md** 比对：
把补录文本切成 k 字骨架滑窗，看多大比例能在原始 md 里找到。
这个比例就是重复率 —— 越低越好（0 表示补进来的全是新内容）。

用法：量重复率.py [report.json] [bundle根] [stage根] [明细条数]
"""
import json
import os
import re
import sys

BUNDLE = "/data/fagui_rag/okf_bundles"
STAGE = "/data/fagui_rag/okf_bundles_stage"
FW = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
KEEP = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]")
MARKS = ("## 附：原文 PDF 补录", "## 附：原文 PDF 表格")


def skel(s):
    return "".join(c for c in (s or "").translate(FW) if KEEP.match(c))


def shingles(s, k=20):
    return {s[i:i + k] for i in range(max(0, len(s) - k + 1))}


def main():
    rep = sys.argv[1] if len(sys.argv) > 1 else "/tmp/repair_batch1.json"
    bundle = sys.argv[2] if len(sys.argv) > 2 else BUNDLE
    stage = sys.argv[3] if len(sys.argv) > 3 else STAGE
    show = int(sys.argv[4]) if len(sys.argv) > 4 else 12

    rows = json.load(open(rep, encoding="utf-8"))
    rows = [r for r in rows if r.get("status") == "ok"]
    worst, tot_app = [], 0
    dup_chars_tot = app_chars_tot = 0
    for r in rows:
        op = os.path.join(bundle, r["rel"])
        sp = os.path.join(stage, r["rel"])
        if not (os.path.isfile(op) and os.path.isfile(sp)):
            continue
        old = open(op, encoding="utf-8", errors="replace").read()
        new = open(sp, encoding="utf-8", errors="replace").read()
        pos = min([p for p in (new.find(m) for m in MARKS) if p >= 0] or [-1])
        if pos < 0:
            continue
        app = new[pos:]
        app_sk = skel(app)
        if len(app_sk) < 40:
            continue
        old_sh = shingles(skel(old))
        k = 20
        windows = [app_sk[i:i + k] for i in range(len(app_sk) - k + 1)]
        dup = sum(1 for w in windows if w in old_sh)
        rate = dup / max(len(windows), 1)
        dup_chars_tot += int(rate * len(app))
        app_chars_tot += len(app)
        tot_app += 1
        worst.append((rate, len(app), r["rel"]))

    worst.sort(reverse=True)
    print(f"含补录段的文档 {tot_app} 份；补录总字 {app_chars_tot:,}")
    print(f"补录内容中【原文已有】的部分约 {dup_chars_tot:,} 字 "
          f"({100.0*dup_chars_tot/max(app_chars_tot,1):.1f}%) —— 即重复率")
    print(f"\n重复率最高的 {show} 份：")
    for rate, ln, rel in worst[:show]:
        print(f"  {100*rate:5.0f}%  补录 {ln:7,d} 字  {rel[:66]}")
    if worst:
        import statistics
        print(f"\n重复率中位数: {100*statistics.median(w[0] for w in worst):.0f}%")


if __name__ == "__main__":
    main()
