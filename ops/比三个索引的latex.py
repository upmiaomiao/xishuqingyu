#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比 index / index_v2 / index_v3：LaTeX 残留量、块数、meta.json。
目的：确认现在这次重建会不会丢掉 09-19 的「LaTeX 归一」修复。"""
import json, re
from pathlib import Path

IDX = Path("/data/fagui_rag")
PAT = {
    "mathrm": re.compile(r"\\mathrm"),
    "times": re.compile(r"\\times|\{?\\times\}?"),
    "upmu": re.compile(r"\\upmu|\\mu\b"),
    "dollar": re.compile(r"\$"),
    "frac": re.compile(r"\\frac"),
}
for name in ("index", "index_v2", "index_v3"):
    d = IDX / name
    cj = d / "chunks.jsonl"
    if not cj.is_file():
        print(f"\n== {name}：无 chunks.jsonl（{d}）")
        continue
    n = 0
    hits = {k: 0 for k in PAT}
    sample = None
    titles = {}
    for line in cj.open(encoding="utf-8"):
        n += 1
        c = json.loads(line)
        t = c.get("text") or ""
        for k, p in PAT.items():
            if p.search(t):
                hits[k] += 1
        if sample is None and PAT["times"].search(t):
            sample = t[:160]
    print(f"\n== {name}：{n} 块")
    print("   LaTeX 残留：", {k: f"{v}({v/n*100:.2f}%)" for k, v in hits.items()})
    if sample:
        print(f"   含 \\times 的样例：{sample}")
    mj = d / "meta.json"
    if mj.is_file():
        print("   meta.json：", mj.read_text(encoding="utf-8").strip()[:300])
    v = d / "vectors.npy"
    if v.is_file():
        print(f"   vectors.npy {v.stat().st_size/1024/1024:.0f} MB，"
              f"修改时间 {__import__('datetime').datetime.fromtimestamp(v.stat().st_mtime):%Y-%m-%d %H:%M}")
