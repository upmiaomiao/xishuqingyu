#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查 GB 18599-2020 的 #8/#12/#13/#15 各自装着什么（决定"#13 掉了"到底要不要紧）。"""
from __future__ import annotations

import json
import re

TARGET = "一般工业固体废物贮存和填埋污染控制标准 GB 18599－2020.md"
for tag, path in (("v1", "/data/fagui_rag/index/chunks.jsonl"),
                  ("v2", "/data/fagui_rag/index_v2/chunks.jsonl")):
    print(f"\n{'='*96}\n【{tag}】")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            c = json.loads(line)
            if (c.get("source") or "").endswith(TARGET) and c.get("chunk_index") in (8, 12, 13, 15):
                t = re.sub(r"\s+", " ", c.get("text") or "")
                has_num = bool(re.search(r"10[⁻\^]|×\s*10|cm/s", t))
                print(f"\n  #{c['chunk_index']}（{len(t)} 字，{'含数值' if has_num else '无 10⁻⁵ 类数值'}）")
                print(f"     {t[:300]}")
