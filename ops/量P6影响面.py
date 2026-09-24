#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量 P6 上线的影响面与工作量（只读 + 一次 32 条的嵌入测速，不改任何线上文件）。

要给出的三个数：
  ① 受影响文档数：用 P6 版 ingest 重切后**块会变**的文档（= 含 markdown 表格的文档 ∪ 待回填文档）
  ② 要重嵌的行数：受影响文档在线上索引里占的全部行（切块边界一变，整篇的块都得重嵌）
  ③ 真实 ETA：拿 32 条文本打一次嵌入接口测吞吐，再按 ② 推算（不猜）

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 量P6影响面.py
"""
from __future__ import annotations

import importlib.util
import io
import json
import re
import sys
import time
from pathlib import Path

LIVE_IDX = Path("/data/fagui_rag/index")
BUNDLE = Path("/data/fagui_rag/okf_bundles")
EMB = "http://127.0.0.1:34004/v1/embeddings"


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


p6 = load("/home/test/ingest_p6.py", "ingest_p6")
live = load("/data/fagui_rag/ingest_okf.py", "ingest_live")

TABLE_SEP = re.compile(r"^\s*\|[\s:|-]+\|\s*$", re.M)


def is_tabley(text: str) -> bool:
    return bool(TABLE_SEP.search(text))


print("① 先看线上索引的规模与来源分布")
n_rows = 0
rows_per_src: dict[str, int] = {}
with io.open(LIVE_IDX / "chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        n_rows += 1
        try:
            s = json.loads(line).get("source", "")
        except Exception:                                           # noqa: BLE001
            s = ""
        rows_per_src[s] = rows_per_src.get(s, 0) + 1
print("   线上 %d 行，来自 %d 个来源" % (n_rows, len(rows_per_src)))

print("\n② 逐份判定：用 P6 版重切，块是否会变（不嵌、只切）")
docs = sorted(BUNDLE.rglob("*.md"))
rel_of = {}
affected, dead_docs = [], 0
tbl_docs = 0
for p in docs:
    rel = str(p.relative_to(BUNDLE))
    rel_of[rel] = p
    t = io.open(p, encoding="utf-8", errors="replace").read()
    has_dead = "![](images/" in t
    if has_dead:
        dead_docs += 1
    tabley = is_tabley(t)
    if tabley:
        tbl_docs += 1
    if not (has_dead or tabley):
        continue
    try:
        _, b1 = live.split_okf(t)
        a = live.chunk_by_paragraph(live.normalize_body(b1))
        _, b2 = p6.split_okf(t)
        b = p6.chunk_by_paragraph(p6.normalize_body(b2))
    except Exception as exc:                                        # noqa: BLE001
        print("   ! 切块失败 %s → %s" % (rel[:50], exc))
        continue
    if a != b:
        affected.append((rel, len(a), len(b)))

print("   bundle 共 %d 份；含死链 %d 份；含 md 表格 %d 份" % (len(docs), dead_docs, tbl_docs))
print("   **重切后块会变的文档：%d 份**" % len(affected))

rows_drop = sum(rows_per_src.get(rel, 0) for rel, _, _ in affected)
rows_new = sum(nb for _, _, nb in affected)
print("\n③ 工作量")
print("   这些文档在线上占 %d 行（要替换掉）" % rows_drop)
print("   P6 重切后它们变成 %d 块（都要重嵌）" % rows_new)
print("   净增 %+d 块；其它 %d 行原样沿用" % (rows_new - rows_drop, n_rows - rows_drop))
miss = [rel for rel, _, _ in affected if rel not in rows_per_src]
print("   ⚠️ 线上索引里找不到对应行的受影响文档：%d 份（可能路径写法不同，需核对）" % len(miss))
for rel in miss[:5]:
    print("      %s" % rel[:90])

print("\n④ 实测嵌入吞吐（32 条一次，只为算 ETA）")
import requests                                                     # noqa: E402
try:
    t0 = time.time()
    r = requests.post(EMB, json={"model": "BGE-M3", "input": ["测速" * 40] * 32}, timeout=300)
    r.raise_for_status()
    el = time.time() - t0
    rate = 32 / el
    print("   32 条用时 %.2fs → %.1f 条/s" % (el, rate))
    print("   按此推算重嵌 %d 块 ≈ %.1f 分钟（实际会因长度更长而更慢，供参考）"
          % (rows_new, rows_new / rate / 60))
except Exception as exc:                                            # noqa: BLE001
    print("   嵌入接口测速失败：%s" % exc)

print("\n⑤ 影响面最大的 10 份（线上块数 → P6 块数）")
for rel, na, nb in sorted(affected, key=lambda x: -(x[2] - x[1]))[:10]:
    print("   %5d → %5d  (%+d)  %s" % (na, nb, nb - na, rel[:74]))
