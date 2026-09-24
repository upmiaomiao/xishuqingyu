# -*- coding: utf-8 -*-
"""只读探针 3：按**审核引擎自己的口径**重建页面文本，再量定位覆盖率。

探针 2 的教训：我用 `get_text("rawdict")`（默认阅读顺序）重建文本，而 audit/parse.py
用的是 `get_text("text", sort=True)` **并且删掉空行**。同一页在表格/分栏处两者顺序不同，
于是摘录"明明在页里"却搜不到 —— 覆盖率高估失败原因是我自己的口径不对，不是数据不好。

本脚本验证三件事：
  ① rawdict(sort=True) 重建出来的文本，是否与审核引擎 page_text 一致；
  ② 字符级定位在**正确口径**下的覆盖率；
  ③ 表格定位档（近似里 span 为空、table 有值）能不能用 find_tables 的 bbox 框出来。
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
from xishu_pipeline.audit_anchor import build_anchors, load_parsed, load_result  # noqa: E402


def pdf_of(name):
    for p in glob.glob(os.path.join(REPORTS, "**", "*.pdf"), recursive=True):
        if os.path.basename(p) == name:
            return p
    return None


def chars_sorted(page):
    """按 sort=True 的顺序取「字符 + bbox」，行末补 \\n，并去掉空行（与 parse.py 同口径）。"""
    lines = []
    for b in page.get_text("rawdict", sort=True).get("blocks", []):
        for l in b.get("lines", []):
            buf, boxes = [], []
            for s in l.get("spans", []):
                for c in s.get("chars", []):
                    ch = c.get("c") or ""
                    if ch:
                        buf.append(ch)
                        boxes.append(c.get("bbox"))
            txt = "".join(buf).strip()
            if txt:                                   # parse.py 删掉了空行
                lines.append((txt, boxes))
    text, allb = [], []
    for txt, boxes in lines:
        # strip 后起点可能变了：按剥离后的字符重新对齐 bbox
        raw = "".join(c for c in txt)
        text.append(raw)
        # 找到该行非空字符的 bbox：按顺序取（strip 只影响首尾空白）
        text.append("\n")
        allb.extend(boxes[-len(raw):] if len(boxes) >= len(raw) else boxes)
        allb.append(None)
    return "".join(text), allb


def find_span_ws(text, quote):
    parts = [p for p in re.split(r"[\s\u3000]+", quote.strip()) if p]
    if not parts:
        return None
    m = re.compile(r"[\s\u3000]*".join(re.escape(p) for p in parts)).search(text)
    if m:
        return m.span()
    squeezed = re.sub(r"[\s\u3000]+", "", text)
    q = re.sub(r"[\s\u3000]+", "", quote)
    i = squeezed.find(q)
    if i < 0:
        return None
    idx, n, start = [], 0, None
    for j, ch in enumerate(text):
        if not ch.isspace() and ch != "\u3000":
            if n == i:
                start = j
            n += 1
            if n == i + len(q):
                return (start, j + 1)
    return None


def rects_for(boxes, start, end, tol=6.0):
    picked = [b for b in boxes[start:end] if b]
    if not picked:
        return []
    picked.sort(key=lambda r: (round(r[1], 1), r[0]))
    rows, cur = [], [picked[0]]
    for r in picked[1:]:
        if abs((r[1] + r[3]) / 2 - (cur[-1][1] + cur[-1][3]) / 2) <= tol:
            cur.append(r)
        else:
            rows.append(cur); cur = [r]
    rows.append(cur)
    return [pymupdf.Rect(min(r[0] for r in row), min(r[1] for r in row),
                         max(r[2] for r in row), max(r[3] for r in row)) for row in rows]


same_pages = diff_pages = 0
grand = {}
tbl_ok = tbl_bad = 0
sample_diff = []
for jf in sorted(os.listdir(RESULTS)):
    if not jf.endswith(".json"):
        continue
    res = load_result(jf[:-5])
    if not res or "items" not in res:
        continue
    fname = res["file"]["name"]
    path = pdf_of(fname)
    parsed = load_parsed(fname, path, allow_parse=False) if path else None
    if not parsed:
        continue
    anchors = build_anchors(res, parsed)
    doc = pymupdf.open(path)

    # ① 口径一致性抽查（每份报告前 5 个有摘录的页）
    checked = set()
    for a in anchors:
        pg = a.get("page")
        if not pg or pg in checked or len(checked) >= 5:
            continue
        checked.add(pg)
        mine, _ = chars_sorted(doc[pg - 1])
        theirs = parsed["page_text"][pg - 1] if pg - 1 < len(parsed["page_text"]) else ""
        if re.sub(r"\s+", "", mine) == re.sub(r"\s+", "", theirs):
            same_pages += 1
        else:
            diff_pages += 1
            if len(sample_diff) < 2:
                sample_diff.append((fname[:20], pg, mine[:120], theirs[:120]))

    for a in anchors:
        lv = a["level"]
        g = grand.setdefault(lv, [0, 0])
        if not a.get("quote") or not a.get("page"):
            continue
        g[0] += 1
        page = doc[a["page"] - 1]
        if a.get("span"):
            text, boxes = chars_sorted(page)
            sp = find_span_ws(text, a["quote"])
            if sp:
                rs = rects_for(boxes, sp[0], sp[1])
                if rs and sum(r.width for r in rs) >= 0.4 * 3 * len(re.sub(r"\s", "", a["quote"])):
                    g[1] += 1
        elif a.get("table") is not None:
            try:
                tbs = page.find_tables().tables
                if a["table"] < len(tbs) and tbs[a["table"]].bbox:
                    g[1] += 1
                    tbl_ok += 1
                else:
                    tbl_bad += 1
            except Exception:
                tbl_bad += 1
    doc.close()

print("① 页面文本口径一致性（抽查）: 一致 %d 页 / 不一致 %d 页" % (same_pages, diff_pages))
for s in sample_diff:
    print("   不一致样例 %s P%s" % (s[0], s[1]))
    print("     我的:", repr(s[2]))
    print("     引擎:", repr(s[3]))
print()
print("② 定位覆盖率（正确口径 + 表格 bbox）")
for k, v in sorted(grand.items()):
    print("   %-4s 有摘录 %3d 条，可框出 %3d 条（%.0f%%）" % (k, v[0], v[1], 100.0 * v[1] / max(v[0], 1)))
q = sum(v[0] for k, v in grand.items() if k != "无证据")
h = sum(v[1] for k, v in grand.items() if k != "无证据")
print("   有证据合计 %d 条，可框出 %d 条（%.0f%%）" % (q, h, 100.0 * h / max(q, 1)))
print("   表格档：框出 %d / 失败 %d" % (tbl_ok, tbl_bad))
