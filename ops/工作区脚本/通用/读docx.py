#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 .docx 抽成纯文本（只用标准库：docx 就是个 zip，正文在 word/document.xml）。

用法：python 读docx.py <docx> [out.txt]
特性：段落逐条编号；表格按「行 | 单元格 | 单元格」还原；不做任何改写。
"""
from __future__ import annotations

import io
import re
import sys
import zipfile

NS_T = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.S)
TAG = re.compile(r"<[^>]+>")


def unescape(s: str) -> str:
    return (s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
             .replace("&apos;", "'").replace("&amp;", "&"))


def para_text(xml_frag: str) -> str:
    parts = NS_T.findall(xml_frag)
    return unescape("".join(parts)).strip()


def main() -> int:
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/docx.txt"
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        xml = z.read("word/document.xml").decode("utf-8", "replace")
    print("压缩包内条目 %d 个；document.xml %d 字节" % (len(names), len(xml)))

    # 把表格与段落按出现顺序处理：先按 <w:tbl> 切，再在片段里按 <w:p> 取
    lines: list[str] = []
    pos = 0
    for m in re.finditer(r"<w:tbl>.*?</w:tbl>", xml, re.S):
        for p in re.finditer(r"<w:p[ >].*?</w:p>", xml[pos:m.start()], re.S):
            t = para_text(p.group(0))
            if t:
                lines.append(t)
        lines.append("【表格】")
        for row in re.finditer(r"<w:tr[ >].*?</w:tr>", m.group(0), re.S):
            cells = [para_text(c.group(0)) for c in
                     re.finditer(r"<w:tc>.*?</w:tc>", row.group(0), re.S)]
            if any(cells):
                lines.append("  | " + " | ".join(cells))
        lines.append("【表格结束】")
        pos = m.end()
    for p in re.finditer(r"<w:p[ >].*?</w:p>", xml[pos:], re.S):
        t = para_text(p.group(0))
        if t:
            lines.append(t)

    text = "\n".join("%4d. %s" % (i, ln) if not ln.startswith("  ") else ln
                     for i, ln in enumerate(lines, 1))
    io.open(out, "w", encoding="utf-8", newline="\n").write(text)
    print("抽出 %d 行 → %s" % (len(lines), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
