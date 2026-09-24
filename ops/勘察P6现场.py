#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读勘察：P6 表格切块上线的现场（2026-09-22 用户说"可以开始了"）。

要回答四个问题：
  ① 线上索引现在是哪一份、多少块？（决定"增量更新"还是"重建"）
  ② 线上 ingest_okf.py 与 P6 版差在哪（P6 版有"表格单独成块 + 来源抬头"）
  ③ 当前 retriever.py 是否已经包含了 P6 那两项检索改动（TOP_K_VEC 提到 60、引用去重）
     —— 若已包含，P6 上线的活就只剩"语料 + 重新切块"；
  ④ 按**当前**语料，有多少份 bundle 的表格是死链图片（= 要回填的规模）。
"""
from __future__ import annotations

import io
import json
import os
import re
from pathlib import Path

RAG = Path("/data/fagui_rag")
LIVE_BUNDLES = RAG / "okf_bundles"
STAGE_BUNDLES = RAG / "okf_bundles_stage"


def sh(cmd: str) -> str:
    return os.popen(cmd).read().strip()


print("=" * 90)
print("① 索引")
print(sh("ls -la /data/fagui_rag/index | head -8"))
meta = RAG / "index" / "meta.json"
if meta.exists():
    d = json.load(io.open(meta, encoding="utf-8"))
    keys = [k for k in ("built_at", "chunks", "n_chunks", "count", "index", "dir", "restatus", "note",
                        "chunks_restatus", "chunks_restatus_note", "retitled", "added") if k in d]
    print("meta.json 关键字段：%s" % {k: d[k] for k in keys})
    print("meta.json 全部字段名：%s" % list(d.keys())[:20])
else:
    print("没有 index/meta.json")
print("index_stage 大小：%s" % sh("du -sh /data/fagui_rag/index_stage"))

print("\n" + "=" * 90)
print("② ingest_okf.py：线上 vs P6 版")
live = io.open(RAG / "ingest_okf.py", encoding="utf-8").read()
p6 = io.open(RAG / "ingest_okf.py.p6_20260916", encoding="utf-8").read()
print("线上 %d 行 / P6 版 %d 行" % (live.count("\n") + 1, p6.count("\n") + 1))
for tag, src in (("线上", live), ("P6", p6)):
    has_tbl = "表格" in src and ("单独成块" in src or "is_table" in src or "table" in src.lower())
    has_head = "【" in src and ("抬头" in src or "标准名" in src or "title" in src)
    print("  %s：表格单独成块迹象=%s ｜ 来源抬头迹象=%s" % (tag, has_tbl, has_head))
# P6 版新增的函数名/关键行
new_lines = [l.strip() for l in p6.splitlines()
             if re.match(r"^(def |TABLE|HEAD|MAX_)", l.strip())]
print("  P6 版里的函数/常量：%s" % new_lines[:14])

print("\n" + "=" * 90)
print("③ 当前 retriever.py 是否已含 P6 两项")
cur = io.open(RAG / "retriever.py", encoding="utf-8").read()
for pat, desc in ((r"TOP_K_VEC\s*=\s*(\d+)", "TOP_K_VEC 初值"),
                  (r"RAG_TOP_K_VEC", "环境变量覆盖"),
                  (r"def diversify|去重|同一来源|per_source|MAX_PER_SOURCE", "引用去重")):
    m = re.findall(pat, cur)
    print("  %-22s → %s" % (desc, m[:3] if m else "**没有**"))
p6r = io.open(RAG / "retriever.py.p6_20260916", encoding="utf-8").read()
print("  P6 版 retriever 的 TOP_K_VEC：%s" % (re.findall(r"TOP_K_VEC\s*=\s*(\d+)", p6r)[:2],
                                        ))

print("\n" + "=" * 90)
print("④ 按当前语料算回填规模")
tot = dead_files = dead_slots = 0
big = []
for p in LIVE_BUNDLES.rglob("*.md"):
    tot += 1
    t = io.open(p, encoding="utf-8", errors="replace").read()
    n = t.count("![](images/")
    if n:
        dead_files += 1
        dead_slots += n
        big.append((n, str(p.relative_to(LIVE_BUNDLES))))
print("线上 bundle：%d 份；含死链图片的 %d 份（%.0f%%）；死链槽位合计 %d 处"
      % (tot, dead_files, 100.0 * dead_files / max(tot, 1), dead_slots))
big.sort(reverse=True)
print("死链最多的 8 份：")
for n, rel in big[:8]:
    print("   %3d 处  %s" % (n, rel[:88]))
print("暂存树份数：%d" % len(list(STAGE_BUNDLES.rglob('*.md'))))

print("\n" + "=" * 90)
print("⑤ 工具与脚本")
print(sh("ls /data/fagui_rag/*.py /data/fagui_rag/*.sh 2>/dev/null | head -26"))
print("PyMuPDF（.venv_tools）：%s" % sh(
    "/data/fagui_rag/.venv_tools/bin/python -c 'import fitz;print(fitz.__doc__)' 2>&1 | head -1"))
print("回填脚本在服务器上吗：%s" % sh("ls /data/fagui_rag/语料正文回填.py /tmp/repair_batch1.json 2>&1 | head -3"))
