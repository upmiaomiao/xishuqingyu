#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""表格正文修复：把 md 里"表格变成死链图片"的位置，用同目录 PDF 的表格文本还原。

背景
----
语料里 2267/3647 份 md 含 `![](images/<hash>.jpg)`，而 images/ 目录全部缺失
（19060 张图，0 张存在）。这些位置原本是标准的限值表 —— 数值因此在索引里完全不存在，
专业问题（"XX 限值是多少"）必然答不出。

已确认 PDF 文本层保留了表格数字（PyMuPDF find_tables 可还原）。

做法
----
1. 扫 md，找到每个 `![](images/*.jpg)` 引用及其前面的 `表N` 题注；
2. 在同目录 PDF 里按题注定位页码，取该页（或紧邻页）的表格；
3. 用标题层级/题注做锚点，把 markdown 表格替换回图片引用处；
4. 全角数字/字母归一化，单元格换行合并。

用法
----
  python3 表格正文修复.py --scan                       # 盘点：多少份可修
  python3 表格正文修复.py --dry-run --limit 8          # 样本试跑，只打印
  python3 表格正文修复.py --write --out D:/修复后       # 实际写出到新目录
"""
from __future__ import annotations

import argparse
import os
import re
import sys

import fitz  # PyMuPDF

IMG_RE = re.compile(r"!\[\]\(images/([0-9A-Za-z]+\.(?:jpg|jpeg|png))\)")
CAP_RE = re.compile(r"[表图]\s*([0-9]{1,2}(?:\.[0-9]{1,2})?)")
FW = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ％～－（）",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz%~-()",
)


def norm(s: str) -> str:
    """归一化用于比对：去空白、全角转半角。"""
    return re.sub(r"\s+", "", (s or "").translate(FW))


def cell(s) -> str:
    if s is None:
        return ""
    t = str(s).translate(FW)
    t = re.sub(r"\s*\n\s*", "", t)          # 单元格内换行合并
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t.replace("|", "\\|")


def to_md(rows) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    fixed = [[cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(fixed[0]) + " |",
           "|" + "|".join([" --- "] * width) + "|"]
    for r in fixed[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def pdf_tables(pdf_path):
    """返回 [(page_no, caption_hint, markdown)]，caption_hint 为该页文本里出现的 表N 号。"""
    doc = fitz.open(pdf_path)
    found = []
    for pno in range(doc.page_count):
        page = doc[pno]
        try:
            tabs = page.find_tables()
        except Exception:
            continue
        if not tabs or not tabs.tables:
            continue
        ptext = norm(page.get_text())
        caps = set(CAP_RE.findall(page.get_text()))
        for tb in tabs.tables:
            md = to_md(tb.extract())
            if md:
                found.append((pno + 1, caps, md))
    # 相邻页合并 caption 线索，便于"题注在上一页、表在本页"的情形
    for i, (pno, caps, md) in enumerate(found):
        near = set(caps)
        for j in (i - 1, i + 1):
            if 0 <= j < len(found):
                near |= found[j][1]
        found[i] = (pno, near, md)
    doc.close()
    return found


def repair(md_path: str, out_path: str | None, dry: bool, verbose: bool):
    d = os.path.dirname(md_path)
    base = os.path.splitext(os.path.basename(md_path))[0]
    sibs = [x for x in os.listdir(d)
            if x.lower().endswith(".pdf") and os.path.splitext(x)[0] == base]
    text = open(md_path, encoding="utf-8").read()
    refs = list(IMG_RE.finditer(text))
    if not refs:
        return None
    if not sibs:
        return {"doc": base, "refs": len(refs), "done": 0, "note": "无同目录 PDF"}

    tabs = pdf_tables(os.path.join(d, sibs[0]))
    used = set()
    out, cursor, done, unmatched = [], 0, 0, 0
    for m in refs:
        head = text[max(0, m.start() - 160):m.start()]
        caps = CAP_RE.findall(head)
        want = caps[-1] if caps else None
        pick = None
        if want:
            for i, (pno, near, md) in enumerate(tabs):
                if i not in used and want in near:
                    pick = i
                    break
        if pick is None:
            for i in range(len(tabs)):
                if i not in used:
                    pick = i
                    break
        out.append(text[cursor:m.start()])
        if pick is None:
            unmatched += 1
            out.append(m.group(0))
        else:
            used.add(pick)
            done += 1
            out.append(f"\n{tabs[pick][2]}\n")
        cursor = m.end()
    out.append(text[cursor:])
    new_text = "".join(out)

    if verbose:
        print(f"--- {base[:60]}")
        print(f"    图片引用 {len(refs)}  成功还原 {done}  未匹配 {unmatched}  "
              f"PDF 表格总数 {len(tabs)}  md {len(text)}→{len(new_text)} 字")
    if not dry and out_path:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        open(out_path, "w", encoding="utf-8").write(new_text)
    return {"doc": base, "refs": len(refs), "done": done,
            "unmatched": unmatched, "pdf_tables": len(tabs)}


def iter_docs(root):
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(".md"):
                yield os.path.join(dp, f)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=r"D:\项目\中节能\0911训练")
    ap.add_argument("--corpora", default="生态环境标准规范,生态环境法律法规,生态环境监管执法")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", default=None, help="只处理文件名含此串的文档")
    a = ap.parse_args()

    docs = []
    for corp in a.corpora.split(","):
        docs += list(iter_docs(os.path.join(a.root, corp)))
    docs = [p for p in docs if IMG_RE.search(open(p, encoding="utf-8").read())]
    if a.only:
        docs = [p for p in docs if a.only in os.path.basename(p)]
    if a.limit:
        docs = docs[:a.limit]
    print(f"含表格死链的文档: {len(docs)}")

    tot_refs = tot_done = tot_un = 0
    for p in docs:
        rel = os.path.relpath(p, a.root)
        op = os.path.join(a.out, rel) if (a.out and a.write) else None
        r = repair(p, op, dry=not a.write, verbose=True)
        if not r:
            continue
        tot_refs += r["refs"]
        tot_done += r["done"]
        tot_un += r.get("unmatched", 0)
    print(f"\n合计：图片引用 {tot_refs}，还原 {tot_done} "
          f"({100.0*tot_done/max(tot_refs,1):.0f}%)，未匹配 {tot_un}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
