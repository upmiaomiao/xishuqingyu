#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PDF 单元格/文本重建的公共工具。

为什么需要它：HJ 169 与多份环评报告 PDF 里，**span 的存储顺序不是阅读顺序**，
下标（CODCr 的 Cr、NH3-N 的 3）会被甩到单元格末尾；直接取 find_tables 的文本会得到
'COD 浓度≥10000mg/L 的有机废液 Cr' 这类错序结果。
做法：把 span 按 y 聚成视觉行（容差 LINE_TOL），行内按 x 排序，再自上而下拼接。
"""
from __future__ import annotations

import re

LINE_TOL = 6.0          # pt：同一视觉行内 y 的允许差（下标约偏 4.2~4.4 pt）
CJK = r"\u3000-\u303f\u4e00-\u9fff\uff00-\uffef"
_WS = re.compile(r"\s+")
_CJK_SPACE = re.compile(rf"(?<=[{CJK}])\s+(?=[{CJK}])")


def clean_cell(s: str) -> str:
    """折叠空白；去掉中文字符之间的空格（换行续行的残留）。"""
    s = _WS.sub(" ", s or "").strip()
    return _CJK_SPACE.sub("", s).strip()


def spans_of(page):
    """页面里所有非空 span。"""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def _inside(span, rect) -> bool:
    x = (span["bbox"][0] + span["bbox"][2]) / 2
    y = (span["bbox"][1] + span["bbox"][3]) / 2
    return rect[0] - 1 <= x <= rect[2] + 1 and rect[1] - 1 <= y <= rect[3] + 1


def cell_text(spans, rect) -> str:
    """按「视觉行聚类 + 行内按 x 排序」重建单元格文本。"""
    got = [s for s in spans if _inside(s, rect)]
    if not got:
        return ""
    got.sort(key=lambda s: (s["bbox"][1] + s["bbox"][3]) / 2)
    lines, cur, cur_y = [], [], None
    for s in got:
        y = (s["bbox"][1] + s["bbox"][3]) / 2
        if cur_y is None or y - cur_y <= LINE_TOL:
            cur.append(s)
            if cur_y is None:
                cur_y = y
        else:
            lines.append(cur)
            cur, cur_y = [s], y
    lines.append(cur)
    parts = []
    for ln in lines:
        ln.sort(key=lambda s: s["bbox"][0])
        parts.append("".join(s["text"] for s in ln))
    return clean_cell("".join(parts))


def rows_of(page):
    """页内所有表格的单元格文本（span 级重建）。返回 [(pno, rows), ...]（pno 为 0 基）。"""
    spans = spans_of(page)
    out = []
    for tb in page.find_tables().tables:
        rows = [["" if c is None else cell_text(spans, c) for c in row.cells]
                for row in tb.rows]
        out.append((page.number, rows))
    return out


def to_markdown(rows) -> str:
    """二维表 → markdown；去掉空行与全空列。"""
    rows = [[(c or "").replace("|", "\\|").strip() for c in r] for r in rows]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [i for i in range(width) if any(r[i] for r in rows)]
    rows = [[r[i] for i in keep] for r in rows]
    head, body = rows[0], rows[1:]
    lines = ["| " + " | ".join(head) + " |",
             "| " + " | ".join("---" for _ in head) + " |"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)