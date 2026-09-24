#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把官方标准文本 PDF 转成带 frontmatter 的 OKF md，并放置原文 PDF。

产物（两处，路径必须对应，否则引用卡片点「查看原文 PDF」会 404）：
  md  : /data/fagui_rag/okf_bundles/<语料>/<名称>.md
  pdf : /data/fagui_pdf/<语料>/<名称>.pdf      # /doc 按 source 去 .md 加 .pdf 找

正文处理：逐页取文本 → 去掉反复出现的页眉页脚与页码 → 按视觉段落分块 →
把 "1 适用范围" 这类编号标题转成 markdown 标题 → 末尾附 `find_tables` 还原的表格。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from collections import Counter

import fitz

BUNDLE = "/data/fagui_rag/okf_bundles"
PDF_ROOT = "/data/fagui_pdf"
CORPUS = "环评导则"

# (标准号, 名称, 取代说明)
GUIDES = [
    ("HJ 2.1-2016", "建设项目环境影响评价技术导则 总纲", "HJ 2.1-2011"),
    ("HJ 2.2-2018", "环境影响评价技术导则 大气环境", "HJ 2.2-2008"),
    ("HJ 2.3-2018", "环境影响评价技术导则 地表水环境", "HJ/T 2.3-93"),
    ("HJ 2.4-2021", "环境影响评价技术导则 声环境", "HJ 2.4-2009"),
    ("HJ 610-2016", "环境影响评价技术导则 地下水环境", "HJ 610-2011"),
    ("HJ 964-2018", "环境影响评价技术导则 土壤环境（试行）", ""),
    ("HJ 19-2022", "环境影响评价技术导则 生态影响", "HJ 19-2011"),
    ("HJ 130-2019", "规划环境影响评价技术导则 总纲", "HJ 130-2014"),
]

HEAD_RE = re.compile(r"^(\d+(?:\.\d+){0,3})\s+(\S.{0,28})$")
APPENDIX_RE = re.compile(r"^附\s*录\s*([A-Z])")
DATE_RE = re.compile(r"(20\d{2})[-年](\d{1,2})[-月](\d{1,2})")


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def page_blocks(text: str):
    """把一页文本按视觉段落切块（连续非空行为一块）。

    编号标题（"1 适用范围"/"5.1 评价等级"）与"附 录 A"单独成块：
    否则会被并进下一段正文，"章节标题"就识别不出来，检索时也少一个定位锚点。
    """
    blocks, cur = [], []

    def flush():
        nonlocal cur
        if cur:
            blocks.append(" ".join(cur))
            cur = []

    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            flush()
            continue
        if HEAD_RE.match(s) or APPENDIX_RE.match(s):
            flush()
            blocks.append(s)
            continue
        cur.append(s)
    flush()
    return blocks


def running_noise(pages_blocks):
    """反复出现在多数页面的短行 = 页眉/页脚/页码。"""
    freq = Counter()
    n = len(pages_blocks)
    for blocks in pages_blocks:
        for b in blocks:
            if len(b) <= 40:
                freq[b] += 1
    return {b for b, c in freq.items() if n >= 3 and c >= max(3, int(n * 0.5))}


def clean_body(pdf_path: str):
    doc = fitz.open(pdf_path)
    pages = [page_blocks(doc[i].get_text()) for i in range(doc.page_count)]
    n_pages = doc.page_count
    doc.close()
    noise = running_noise(pages)

    out, heads = [], []
    for blocks in pages:
        for b in blocks:
            if b in noise:
                continue
            if re.fullmatch(r"[\d\s\-—－]{1,8}", b):     # 纯页码
                continue
            if APPENDIX_RE.match(b):
                out.append(f"\n## {b}\n")
                continue
            m = HEAD_RE.match(b)
            if m and not b.endswith(("。", "，", "；", "：", ")", "）")):
                heads.append(m.group(1))
                out.append(f"\n### {m.group(1)} {m.group(2)}\n")
            else:
                out.append(b)
    body = "\n\n".join(out)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body, heads, n_pages


def table_appendix(pdf_path: str, limit=60):
    doc = fitz.open(pdf_path)
    blocks, seen = [], set()
    for pno in range(doc.page_count):
        try:
            tabs = doc[pno].find_tables()
        except Exception:
            continue
        if not tabs or not tabs.tables:
            continue
        for tb in tabs.tables:
            try:
                rows = tb.extract()
            except Exception:
                continue
            if not rows or max(len(r) for r in rows) < 2:
                continue
            width = max(len(r) for r in rows)
            fixed = [[norm(str(c)) if c is not None else "" for c in r] + [""] * (width - len(r))
                     for r in rows]
            md = ["| " + " | ".join(fixed[0]) + " |",
                  "|" + "|".join([" --- "] * width) + "|"]
            for r in fixed[1:]:
                md.append("| " + " | ".join(r) + " |")
            key = norm("".join(fixed[0]) + "".join(fixed[-1]))
            if key in seen:
                continue
            seen.add(key)
            blocks.append(f"<!-- 第 {pno+1} 页 -->\n\n" + "\n".join(md))
            if len(blocks) >= limit:
                break
    doc.close()
    return blocks


def frontmatter(sid: str, name: str, supersedes: str, body: str, rel: str) -> str:
    dates = DATE_RE.findall(body)
    issued = implemented = ""
    if dates:
        issued = "-".join([dates[0][0], dates[0][1].zfill(2), dates[0][2].zfill(2)])
        if len(dates) > 1:
            implemented = "-".join([dates[1][0], dates[1][1].zfill(2), dates[1][2].zfill(2)])
    lines = [
        "---",
        "type: standard",
        f"title: {name}",
        f"description: 环境标准/规范（{sid}）：{name}——环境影响评价技术导则正文",
        "tags:",
        "- 标准规范",
        "- 环境影响评价",
        "- 国家",
        "- " + sid.split()[0],
        "status: 现行",
        "region_type: 国家",
        "region: 全国",
        f"standard_id: {sid}",
        "issuer:",
        "- 生态环境部",
    ]
    if issued:
        lines.append(f"issued: {issued}")
    if implemented:
        lines.append(f"implemented: {implemented}")
    if supersedes:
        lines += ["supersedes:", f"- standard_id: {supersedes}"]
    lines.append("doc_role: 导则正文")
    lines.append(f"source_path: {rel}")
    lines.append("---")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/fagui_rag/guides_pdf")
    ap.add_argument("--bundle", default=BUNDLE)
    ap.add_argument("--pdf-root", default=PDF_ROOT)
    ap.add_argument("--corpus", default=CORPUS)
    ap.add_argument("--no-tables", action="store_true")
    a = ap.parse_args()

    md_dir = os.path.join(a.bundle, a.corpus)
    pdf_dir = os.path.join(a.pdf_root, a.corpus)
    os.makedirs(md_dir, exist_ok=True)
    os.makedirs(pdf_dir, exist_ok=True)

    for sid, name, sup in GUIDES:
        fname = f"{sid} {name}"
        src = os.path.join(a.src, sid.replace(" ", "_") + ".pdf")
        if not os.path.isfile(src):
            print(f"[跳过] 无 PDF: {src}")
            continue
        body, heads, n_pages = clean_body(src)
        tabs = [] if a.no_tables else table_appendix(src)
        rel = f"{a.corpus}/{fname}.md"
        fm = frontmatter(sid, name, sup, body, rel)
        parts = [fm, "", f"# {name}（{sid}）", "", body]
        if tabs:
            parts += ["", f"## 附：原文 PDF 表格（结构化还原，共 {len(tabs)} 张）", ""]
            parts += ["\n\n".join(tabs)]
        text = "\n".join(parts).rstrip() + "\n"

        md_path = os.path.join(md_dir, fname + ".md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(text)
        shutil.copy2(src, os.path.join(pdf_dir, fname + ".pdf"))
        print(f"✓ {sid}  {n_pages} 页 → md {len(text):,} 字  "
              f"章节标题 {len(heads)} 个  表格 {len(tabs)} 张")
        print(f"    md : {md_path}")
        print(f"    pdf: {os.path.join(pdf_dir, fname + '.pdf')}")

    # 抽样打印第一份的开头，便于人工核对格式
    first = os.path.join(md_dir, GUIDES[0][0] + " " + GUIDES[0][1] + ".md")
    if os.path.isfile(first):
        print("\n===== 格式抽样（前 1200 字）=====")
        print(open(first, encoding="utf-8").read()[:1200])


if __name__ == "__main__":
    sys.exit(main())
