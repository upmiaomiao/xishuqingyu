#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探针：拿第 10 题（HG/T 3650-2012）问线上站点，看引用里有没有「已废止」的块。

用法：python 验已废止降权.py 前置|后置
输出：_工作记录/实跑已废止_<标签>.json
"""
from __future__ import annotations

import io
import json
import sys
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
SITE = "http://10.201.31.10:8011/hybrid_search"
ABOLISHED = ("已废止", "废止", "已失效", "已作废")

rows = [json.loads(l) for l in
        io.open(WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl", encoding="utf-8")]
Q = [r for r in rows if r["序号"] == 10][0]["题目"]

req = urllib.request.Request(
    SITE, data=json.dumps({"query": Q}).encode("utf-8"),
    headers={"Content-Type": "application/json"})
d = json.loads(urllib.request.urlopen(req, timeout=600).read().decode("utf-8"))

label = sys.argv[1] if len(sys.argv) > 1 else "未标注"
print(f"【{label}】route={d.get('route')} 耗时={d.get('latency_s')}s "
      f"模型={d.get('model')} 引用 {len(d.get('sources') or [])} 条")
n_ab = 0
for s in d.get("sources") or []:
    st = str(s.get("status") or "")
    flag = "  ← 已废止" if st in ABOLISHED else ""
    if flag:
        n_ab += 1
    print(f"  [{s.get('index')}] type={s.get('doc_type')!s:<9} status={st or '（空）':<6} "
          f"rerank={(s.get('rerank_score') or 0):.3f}  {str(s.get('title'))[:38]}{flag}")
print(f"→ 已废止引用 {n_ab} 条 / 共 {len(d.get('sources') or [])} 条；"
      f"答案 {len(d.get('answer') or '')} 字")

out = WS / "_工作记录" / f"实跑已废止_{label}.json"
out.write_text(json.dumps({"label": label, "query": Q,
                           "latency_s": d.get("latency_s"), "route": d.get("route"),
                           "sources": d.get("sources"), "answer": d.get("answer"),
                           "n_abolished": n_ab}, ensure_ascii=False, indent=1),
               encoding="utf-8")
print(f"→ {out}")
