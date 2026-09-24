# -*- coding: utf-8 -*-
"""定"修订式交付"有没有底子：① PDF 是文本版还是扫描件 ② 证据摘录能不能在这页原文里找到
③ _cache 里存了什么。只读。"""
import glob
import json
import os
import sys

sys.path.insert(0, "/data/eia_audit")
try:
    import fitz  # pymupdf
except Exception as exc:
    print("pymupdf 缺失：", exc)
    fitz = None

print("===== _cache 里有什么 =====")
for root, dirs, files in os.walk("/data/eia_audit/_cache"):
    for f in files[:8]:
        p = os.path.join(root, f)
        print("  %9d  %s" % (os.path.getsize(p), p))
    if len(files) > 8:
        print("  …共 %d 个文件" % len(files))

print()
print("===== PDF 文本可抽取性 + 证据能否回定位 =====")
rep_dir = "/data/eia_reports"
res_dir = "/data/eia_audit/_审核结果"

for jf in sorted(glob.glob(os.path.join(res_dir, "*.json"))):
    base = os.path.basename(jf)
    if base == "gold评测.json":
        continue
    d = json.load(open(jf, encoding="utf-8"))
    pdf = os.path.join(rep_dir, d["file"]["name"])
    print("-" * 90)
    print("报告：", d["file"]["name"], "页数：", d["file"].get("pages"), "存在：", os.path.isfile(pdf))
    if not os.path.isfile(pdf) or fitz is None:
        continue
    doc = fitz.open(pdf)
    n = doc.page_count
    # 抽 5 页看文本量
    lens = []
    for i in range(min(5, n)):
        lens.append(len(doc[i].get_text().strip()))
    print("  前 5 页可抽文本长度：", lens, "→", "文本版" if max(lens) > 200 else "疑似扫描件")
    # 证据回定位：在第 page 页找 quote
    tot = found = 0
    miss = []
    for it in d.get("items", []):
        for e in (it.get("证据") or []):
            pg, q = e.get("page"), str(e.get("quote") or "")
            if not pg or not q or pg > n:
                continue
            tot += 1
            text = doc[pg - 1].get_text()
            key = "".join(q.split())[:12]
            flat = "".join(text.split())
            if key and key in flat:
                found += 1
            else:
                miss.append((it.get("审核项"), pg, q[:40]))
    print("  证据回定位：%d/%d 能在该页原文里逐字找到" % (found, tot))
    for m in miss[:4]:
        print("     找不到：%s P%s 「%s」" % m)
    doc.close()
