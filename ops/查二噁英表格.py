#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""二噁英"表格没进池"到底怪谁：库里有没有带限值数值的表格块？

三种可能：
  A) 索引里根本没有这些表格块（PDF→md 转换时表格丢了）→ 语料问题，检索层无解
  B) 有，但没进候选池 → 召回/配额问题，还能再修
  C) 有、也在池里，只是重排分低 → 选取问题
"""
from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

spec = importlib.util.spec_from_file_location("rv2", "/data/fagui_rag/retriever_v2.py"
                                              if Path("/data/fagui_rag/retriever_v2.py").exists()
                                              else "/data/fagui_rag/retriever.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

NEEDLES = ("GB 28664", "GB 13801", "DB 13_ 2698", "18484", "18485", "GB 15581")
PAT = re.compile(r"二噁英")

print("===== 索引普查：这些标准的块里，有多少同时含“二噁英”和具体数值 =====")
hit_stats: dict[str, dict] = {}
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as fh:
    for line in fh:
        c = json.loads(line)
        src = c.get("source") or ""
        for nd in NEEDLES:
            if nd in src:
                st = hit_stats.setdefault(nd, {"files": set(), "chunks": 0, "with_dex": 0, "with_num": 0})
                st["files"].add(src)
                st["chunks"] += 1
                t = c.get("text") or ""
                if "二噁英" in t:
                    st["with_dex"] += 1
                    if re.search(r"\d+\.\d+", t):
                        st["with_num"] += 1
                        if st["with_num"] <= 2:
                            print(f"\n  [{nd}] {src[-60:]}")
                            print("      ", re.sub(r"\s+", " ", t)[:300])
for nd, st in hit_stats.items():
    print(f"\n{nd}: 文件 {len(st['files'])} 份，块 {st['chunks']}，"
          f"含“二噁英” {st['with_dex']}，其中带小数数值 {st['with_num']}")

print("\n\n===== 这些问题：带数值的二噁英块进池了吗 =====")
r = m.Retriever()
q = "二噁英的排放限值是多少？"
qv = r.embed(q)
hits = r.recall(qv, top_k_vec=20)
pool = [(i, s, r.chunks[i]) for i, s in hits]
dex = [(i, s, c) for i, s, c in pool if "二噁英" in (c.get("text") or "")]
print(f"候选池 {len(pool)} 条，其中正文含“二噁英”的 {len(dex)} 条")
for i, s, c in dex:
    t = re.sub(r"\s+", " ", c.get("text") or "")
    print(f"  vec={s:.4f} {c.get('source','')[-46:]}  chunk#{c.get('chunk_index')}")
    print(f"      {t[:150]}")
