#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对线上版与 P6 版 ingest 的**逐函数差异**（只读，不写盘）。

为什么必须核对：建 P6 索引时发现"变更来源 4054 ／ 沿用 0" —— 所有来源的 text 都变了。
要搞清变在哪一层：
  · 只是 chunk 正文的切块边界（表格逻辑）？→ 影响面就是"含表格的文档"，可接受；
  · 还是**来源抬头/其它公共逻辑**变了？→ 那是全库 26 万块都被改动，风险级别完全不同，
    应当改成"只把表格逻辑移植到线上版"，而不是整体换版。
"""
from __future__ import annotations

import io
import re

PAIRS = [("/data/fagui_rag/ingest_okf.py", "线上版"),
         ("/data/fagui_rag/ingest_okf.py.p6_20260916", "P6 版")]
FUNCS = ["context_header", "chunk_by_paragraph", "make_embed_text", "normalize_body",
         "split_okf", "_is_table", "_split_table"]


def get_func(src: str, name: str) -> str:
    m = re.search(r"^def %s\(.*?(?=^def |\Z)" % re.escape(name), src, re.M | re.S)
    return m.group(0).rstrip() if m else "(无此函数)"


def main() -> int:
    bodies = {}
    for path, tag in PAIRS:
        src = io.open(path, encoding="utf-8").read()
        bodies[tag] = {f: get_func(src, f) for f in FUNCS}
        print("%s：%d 行" % (tag, src.count("\n") + 1))

    for f in FUNCS:
        a, b = bodies["线上版"][f], bodies["P6 版"][f]
        if a == b:
            print("\n【%s】两版逐字相同 ✅（%d 行）" % (f, a.count("\n") + 1))
            continue
        print("\n【%s】有差异：" % f)
        al, bl = a.splitlines(), b.splitlines()
        import difflib
        for line in difflib.unified_diff(al, bl, "线上版", "P6版", lineterm="", n=1):
            print("   " + line[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
