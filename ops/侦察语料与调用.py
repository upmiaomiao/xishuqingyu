# -*- coding: utf-8 -*-
"""侦察二：① 站点怎么调 retrieve()（top_k）② kg.py 的依赖 ③ 语料里有没有安吉/平阳"""
import collections
import json
import re

IDX = "/data/fagui_rag/index/chunks.jsonl"

print("===== 关键词在索引里的块数 / 涉及文件数 =====")
for kw in ("安吉", "平阳", "晋城", "永济", "乾县", "汕头", "泉域", "岩溶"):
    n = 0
    files = collections.Counter()
    title_hit = collections.Counter()
    with open(IDX, encoding="utf-8") as f:
        for line in f:
            if kw not in line:
                continue
            c = json.loads(line)
            n += 1
            files[c.get("source")] += 1
            if kw in (c.get("title") or ""):
                title_hit[c.get("title")] += 1
    print("%-6s 块 %6d  文件 %4d  标题含该词 %4d" % (kw, n, len(files), sum(title_hit.values())))
    for k, v in files.most_common(3):
        print("        %5d  %s" % (v, k))

print()
print("===== 站点 pipeline.py 里的检索调用 =====")
for path in ("/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py",):
    with open(path, encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            if re.search(r"retriever\.retrieve|top_k_final|top_k_vec|normalize_sources|graph_evidence|verify_citations", line):
                print("%4d: %s" % (i, line.rstrip()))

print()
print("===== kg.py 顶部依赖 =====")
with open("/home/test/xishu_qingyu_serve/xishu_pipeline/kg.py", encoding="utf-8") as f:
    for i, line in enumerate(f, 1):
        if i > 20:
            break
        print("%3d: %s" % (i, line.rstrip()))
