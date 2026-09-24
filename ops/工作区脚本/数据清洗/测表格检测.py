#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在服务器上直接测某份 PDF 的表格检测与还原结果（隔离"检测不到"还是"被跳过"）。"""
import json
import sys

sys.path.insert(0, "/tmp")
from importlib import import_module

m = import_module("语料正文回填")

KEY = sys.argv[1] if len(sys.argv) > 1 else "储油库大气污染物排放标准（GB 20950—2020"
targets = json.load(open("/tmp/回填清单.json", encoding="utf-8"))
hit = [t for t in targets if KEY in t["rel"]]
if not hit:
    raise SystemExit(f"清单里没有匹配 {KEY} 的文档")
t = hit[0]
PDF = t["pdf"]
print(f"文档: {t['rel'][:90]}")
print(f"PDF : {PDF}\n")

tabs = m.pdf_tables(PDF)
print(f"pdf_tables 检出 {len(tabs)} 张表")
for pno, md in tabs:
    sk = m.skel_map(md)[0]
    print(f"  第 {pno} 页  骨架 {len(sk)} 字")
    print("   " + md.replace("\n", " ⏎ ")[:200])

# 看是哪个条件把它挡掉的
md_path = ("/data/fagui_rag/okf_bundles_stage/生态环境标准规范/大气环境保护/大气环境保护_附件125/"
           "大气固定源污染物排放标准_附件51/储油库大气污染物排放标准 GB 20950—2020代替GB 20950—2007_附件/"
           "储油库大气污染物排放标准（GB 20950—2020代替GB 20950—2007）/"
           "储油库大气污染物排放标准（GB 20950—2020代替GB 20950—2007）.md")
text = open(md_path, encoding="utf-8").read()
sh, _ = m.md_shingles(text)
for pno, md in tabs:
    sk = m.skel_map(md)[0]
    cov = m.is_covered(sk, sh, cover=0.95)
    print(f"  第 {pno} 页: 骨架 {len(sk)} 字, 判定已存在={cov}  → {'跳过' if cov else '应补入'}")
