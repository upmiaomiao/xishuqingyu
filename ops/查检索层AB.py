#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索层 A/B 影子验证：同一批问题，分别走「改造前」和「改造后」两套实现。

不碰线上进程、不改任何线上文件，只是自己 import 一份跑一遍。
用法：
    python 查检索层AB.py --impl old --out /tmp/ab_old.json
    python 查检索层AB.py --impl new --out /tmp/ab_new.json
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path

IMPL_PATH = {
    "old": "/data/fagui_rag/retriever.py",              # 线上正在跑的
    "new": "/data/fagui_rag/_staging/retriever_v2.py",  # 候选版本
}

QUERIES = [
    # —— 依题型：改造前被报告挤掉依据的（本次要修的）——
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
    "二噁英的排放限值是多少？",
    "GB 18599 一般工业固体废物贮存的标准要求",
    "排污许可证的有效期是多久？",
    "未批先建的法律责任和罚款幅度",
    "危险废物鉴别的国家标准是什么",
    "河北省大气污染防治条例对工业污染如何规定",
    # —— 案例型：改造后必须照样引到报告（反向断言用）——
    "济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？",
    "江苏苏州物资再生有限公司这个项目的建设内容是什么？",
    # —— 中性问题 ——
    "中央生态环境保护督察通报了哪些典型案例",
]


def load_impl(which: str):
    p = IMPL_PATH[which]
    spec = importlib.util.spec_from_file_location(f"retriever_{which}", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--impl", choices=["old", "new"], required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    t0 = time.time()
    mod = load_impl(args.impl)
    r = mod.Retriever()
    print(f"[{args.impl}] 载入耗时 {time.time() - t0:.1f}s", flush=True)

    rows = []
    for q in QUERIES:
        t1 = time.time()
        try:
            got = r.retrieve(q, 20, 5)
            err = ""
        except Exception as e:  # noqa: BLE001
            got, err = [], f"{type(e).__name__}: {e}"
        dt = time.time() - t1
        rows.append({
            "query": q,
            "seconds": round(dt, 2),
            "error": err,
            "sources": [{
                "type": s.get("type"),
                "corpus": (s.get("source") or "").split("/")[0],
                "source": s.get("source"),
                "title": s.get("title"),
                "chunk_index": s.get("chunk_index"),
                "rerank": s.get("rerank_score"),
                "vec": s.get("vec_sim"),
                "text": (s.get("text") or "")[:600],
            } for s in got],
        })
        n_auth = sum(1 for s in rows[-1]["sources"] if s["corpus"] in
                     ("生态环境标准规范", "生态环境法律法规", "环评导则"))
        print(f"  [{args.impl}] {dt:5.1f}s  依据 {n_auth}/5  {q[:38]}", flush=True)

    Path(args.out).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[{args.impl}] 结果写入 {args.out}", flush=True)


if __name__ == "__main__":
    main()
