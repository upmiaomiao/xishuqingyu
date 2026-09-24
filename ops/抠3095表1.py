#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：把 GB 3095—2026 bundle 里的"表1 环境空气污染物基本项目浓度限值"原文抠出来。

目的：判断两件事 ——
  ① 表里的数字在 md 里是否完整（若完整，可以安全地转成一句"文字表述"，
     像 09-21 给 GB 18484 做的那样，让限值数字真正进索引）；
  ② 过渡阶段 / 第二阶段两列到底各是多少（问答错例就是答成了第二阶段的值）。
"""
from __future__ import annotations

import re
from pathlib import Path

B = Path("/data/fagui_rag/okf_bundles")
PAT = "环境空气质量标准（GB 3095—2026）"
FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

for p in sorted(B.rglob("*.md")):
    rel = p.relative_to(B).as_posix()
    if PAT not in rel:
        continue
    t = p.read_text(encoding="utf-8", errors="replace")
    m = FM.match(t)
    body = t[m.end():] if m else t
    print("=" * 100)
    print(rel)
    print("=" * 100)
    # 表1/表2 附近区域：从"表1"出现处往后 3000 字符
    for kw in ("表1", "表 1", "浓度限值"):
        for mm in re.finditer(re.escape(kw), body):
            seg = body[mm.start():mm.start() + 2600]
            if re.search(r"\d{2}", seg):
                print(f"\n----- 「{kw}」@{mm.start()} -----")
                print(seg)
                break
        else:
            continue
        break
    print("\n\n（表 1 之后是否有表格分隔符：| 计数 = %d，制表符计数 = %d）"
          % (body.count("|"), body.count("\t")))
