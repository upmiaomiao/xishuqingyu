#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一个 PDF 的正文与表格抽成文本（给"官方原文入库"用）。

用法：/data/fagui_rag/.venv_tools/bin/python 取标准文本.py <pdf> [out.txt]
输出：out.txt（每页文本 + 用 find_tables 还原的表格 markdown），并在屏幕上打印摘要。
"""
from __future__ import annotations

import io
import sys

import fitz


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    pdf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/" + pdf.split("/")[-1].rsplit(".", 1)[0] + ".txt"
    doc = fitz.open(pdf)
    parts = []
    n_tab = n_row = 0
    for i, page in enumerate(doc, 1):
        parts.append("\n==== 第 %d 页 ====\n" % i)
        parts.append(page.get_text("text"))
        try:
            for t in page.find_tables():
                rows = t.extract()
                n_tab += 1
                n_row += len(rows)
                parts.append("\n--- 表 %d（第 %d 页，%d 行）---\n" % (n_tab, i, len(rows)))
                for r in rows:
                    cells = ["" if c is None else str(c).replace("\n", " ").strip() for c in r]
                    parts.append("| " + " | ".join(cells) + " |")
        except Exception as exc:                                    # noqa: BLE001
            parts.append("\n（本页表格还原失败：%s）\n" % exc)
    text = "".join(parts)
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print("页数 %d ｜ 还原表格 %d 张 / %d 行 ｜ 文本 %d 字" % (len(doc), n_tab, n_row, len(text)))
    print("输出 → %s" % out)
    # 打印含"限值/表"的行，便于一眼确认拿到没拿到数字
    for ln in text.splitlines():
        s = ln.strip()
        if ("限值" in s or s.startswith("表") or "| " in s) and any(c.isdigit() for c in s):
            print("   " + s[:150])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
