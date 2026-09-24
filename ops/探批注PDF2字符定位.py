# -*- coding: utf-8 -*-
"""只读探针 2：用**字符级 bbox** 定位摘录（比 search_for 可靠得多）。

背景：探针 1 实测 `page.search_for(整条摘录)` 只命中 34%，而且退化成"片段搜索"后
会返回 6pt 宽的竖排窄条 —— 拿它画高亮就是**画错地方**，比不画更糟。

做法：把页面拆成「字符 + bbox」序列（rawdict），拼成整页文本，再用
**空白不敏感**的匹配找到摘录对应的字符区间，取这些字符的 bbox 并集 → 高亮。
好处：跨行、表格里、被空格/换行切开的摘录都能框对。

本脚本只读报告、只算命中率，不写任何文件（除了 /tmp 下的小样张）。
"""
import glob
import json
import os
import re
import sys

import pymupdf

REPORTS = "/data/eia_reports"
RESULTS = "/data/eia_audit/_审核结果"
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
from xishu_pipeline.audit_anchor import load_result, build_anchors, load_parsed  # noqa: E402


def pdf_of(name):
    for p in glob.glob(os.path.join(REPORTS, "**", "*.pdf"), recursive=True):
        if os.path.basename(p) == name:
            return p
    return None


def chars_of(page):
    """整页「字符序列 + bbox 序列」。行末补 \\n（与 get_text('text') 的口径一致）。"""
    text, boxes = [], []
    d = page.get_text("rawdict")
    for b in d.get("blocks", []):
        for l in b.get("lines", []):
            for s in l.get("spans", []):
                for c in s.get("chars", []):
                    ch = c.get("c") or ""
                    if not ch:
                        continue
                    text.append(ch)
                    boxes.append(c.get("bbox"))
            text.append("\n")
            boxes.append(None)
    return "".join(text), boxes


def find_span_ws(text, quote):
    """空白不敏感的查找：把摘录里每段之间的空白当作可有可无。返回 (start, end)。"""
    parts = [p for p in re.split(r"[\s\u3000]+", quote.strip()) if p]
    if not parts:
        return None
    pat = re.compile(r"[\s\u3000]*".join(re.escape(p) for p in parts))
    m = pat.search(text)
    if m:
        return m.span()
    # 退一步：去掉中文之间的空白再试
    squeezed = re.sub(r"[\s\u3000]+", "", text)
    q = re.sub(r"[\s\u3000]+", "", quote)
    i = squeezed.find(q)
    if i < 0:
        return None
    # 把 squeezed 的下标映射回原文本
    idx, n = [], 0
    for j, ch in enumerate(text):
        if not ch.isspace() and ch != "\u3000":
            if n == i:
                start = j
            n += 1
            if n == i + len(q):
                return (start, j + 1)
    return None


def rects_for(boxes, start, end):
    """字符区间 → 按行分组的矩形（行内取并集）。"""
    picked = [b for b in boxes[start:end] if b]
    if not picked:
        return []
    picked.sort(key=lambda r: (round(r[1], 1), r[0]))
    rows, cur = [], [picked[0]]
    for r in picked[1:]:
        cy = (cur[-1][1] + cur[-1][3]) / 2
        if abs((r[1] + r[3]) / 2 - cy) <= 6:
            cur.append(r)
        else:
            rows.append(cur)
            cur = [r]
    rows.append(cur)
    out = []
    for row in rows:
        x0 = min(r[0] for r in row); y0 = min(r[1] for r in row)
        x1 = max(r[2] for r in row); y1 = max(r[3] for r in row)
        out.append(pymupdf.Rect(x0, y0, x1, y1))
    return out


print("=== 逐份报告：字符级定位能覆盖多少条 ===")
grand = {}
for jf in sorted(os.listdir(RESULTS)):
    if not jf.endswith(".json"):
        continue
    res = load_result(jf[:-5])
    if not res or "items" not in res:
        continue
    fname = res["file"]["name"]
    path = pdf_of(fname)
    if not path:
        print("  找不到 PDF：", fname)
        continue
    parsed = load_parsed(fname, path, allow_parse=False)
    if not parsed:
        print("  没有解析缓存：", fname)
        continue
    anchors = build_anchors(res, parsed)
    doc = pymupdf.open(path)
    stat = {}
    for a in anchors:
        lv = a["level"]
        stat.setdefault(lv, [0, 0])          # [有摘录, 定位成功]
        if not a.get("quote") or not a.get("page"):
            continue
        stat[lv][0] += 1
        try:
            page = doc[a["page"] - 1]
            text, boxes = chars_of(page)
            sp = find_span_ws(text, a["quote"])
            if not sp:
                continue
            rs = rects_for(boxes, sp[0], sp[1])
            if not rs:
                continue
            w = sum(r.width for r in rs)
            # 几何合理性：竖直窄条 = 定位错了，宁可不画
            if w < 3 * len(re.sub(r"\s", "", a["quote"])) * 0.4:
                stat[lv][1] += 0
            else:
                stat[lv][1] += 1
        except Exception as exc:
            print("    异常 P%s %s" % (a.get("page"), exc))
    for k, v in stat.items():
        g = grand.setdefault(k, [0, 0])
        g[0] += v[0]; g[1] += v[1]
        print("  %-38s %-4s 有摘录 %2d 条 → 能框出 %2d 条" % (fname[:38], k, v[0], v[1]))
    doc.close()

print("\n=== 合计 ===")
for k, v in sorted(grand.items()):
    print("  %-4s 有摘录 %3d 条，可框出 %3d 条（%.0f%%）" % (k, v[0], v[1], 100.0 * v[1] / max(v[0], 1)))
tot_q = sum(v[0] for k, v in grand.items() if k != "无证据")
tot_h = sum(v[1] for k, v in grand.items() if k != "无证据")
print("  有证据合计 %d 条，可框出 %d 条（%.0f%%）" % (tot_q, tot_h, 100.0 * tot_h / max(tot_q, 1)))
