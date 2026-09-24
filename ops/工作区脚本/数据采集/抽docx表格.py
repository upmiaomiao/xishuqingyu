#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库数字化 (1)：抓官方 docx 并把表格结构化。

分类管理名录的价值全在**附表**（行业 → 报告书/报告表/登记表 + 阈值条件），
docx 里的表格是结构化的，比 PDF 抽取可靠得多，因此优先用 docx。

实现只用标准库（zipfile + ElementTree 解析 word/document.xml），
不引 python-docx，避免在服务器上装包。

用法：
  python3 抽docx表格.py download <url> <out.docx>
  python3 抽docx表格.py tables <docx> [--limit N] [--json out.json]
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import zipfile
import xml.etree.ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}


def download(url: str, out: str) -> int:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        raw = r.read()
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(raw)
    print(f"下载 {len(raw):,} 字节 → {out}")
    print(f"  头部: {raw[:8]!r}")
    return len(raw)


def para_text(p) -> str:
    return "".join(t.text or "" for t in p.iter(W + "t")).strip()


def cell_text(tc) -> str:
    return re.sub(r"\s+", " ", "".join(t.text or "" for t in tc.iter(W + "t"))).strip()


def parse_docx(path: str):
    """按文档顺序返回 [(kind, 内容)]：kind ∈ heading/para/table。"""
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    body = root.find(W + "body")
    out = []
    for el in list(body):
        tag = el.tag
        if tag == W + "p":
            t = para_text(el)
            if t:
                style = ""
                ppr = el.find(W + "pPr")
                if ppr is not None:
                    st = ppr.find(W + "pStyle")
                    if st is not None:
                        style = st.get(W + "val", "")
                out.append(("heading" if style.lower().startswith("heading") else "para", t))
        elif tag == W + "tbl":
            rows = []
            for tr in el.findall(W + "tr"):
                cells = [cell_text(tc) for tc in tr.findall(W + "tc")]
                if any(cells):
                    rows.append(cells)
            if rows:
                out.append(("table", rows))
    return out


def main():
    cmd = sys.argv[1]
    if cmd == "download":
        download(sys.argv[2], sys.argv[3])
        return 0

    path = sys.argv[2]
    limit = 0
    json_out = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    if "--json" in sys.argv:
        json_out = sys.argv[sys.argv.index("--json") + 1]

    items = parse_docx(path)
    n_par = sum(1 for k, _ in items if k != "table")
    tables = [c for k, c in items if k == "table"]
    print(f"文档元素 {len(items)} 个：段落/标题 {n_par}，表格 {len(tables)} 张")
    for i, rows in enumerate(tables, 1):
        width = max(len(r) for r in rows)
        print(f"  表 {i}: {len(rows)} 行 × {width} 列")

    # 记录每张表前面的最近标题，便于把表归到章节
    ctx, cur = [], ""
    result = []
    for kind, content in items:
        if kind == "heading":
            cur = content
        elif kind == "para" and len(content) < 40 and re.match(r"^[一二三四五六七八九十\d]+[、.．]", content):
            cur = content
        elif kind == "table":
            result.append({"context": cur, "rows": content})

    if limit:
        for item in result[:limit]:
            print(f"\n--- 上文: {item['context'][:60]}")
            for r in item["rows"][:6]:
                print("   | " + " | ".join(c[:24] for c in r))
    if json_out:
        with open(json_out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        print(f"\n表格 JSON → {json_out}（{len(result)} 张）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
