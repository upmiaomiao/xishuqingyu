#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""B3 探针：GB 3095—2026 的限值表，回填前后各是什么样（只读）。

B3 的原话（`2026-09-22-用户反馈可改项评估.md` 第 532 行）：
  「`GB 3095—2026` 表1/表2 在语料里是**图片** —— 数字从来没进过索引」。
这次全量回填（结构化表格还原 15,862 张）应当把它补回来。用三条探针看：
  ① 死链图片处数（回填前 vs 回填后）
  ② 表附近的原文片段（能不能看到浓度限值数字）
  ③ 逐项限值的特征串（SO2/NO2/PM10/PM2.5 的 年平均/24 小时 数值）
"""
from __future__ import annotations

import io
import re
from pathlib import Path

TREES = ("okf_bundles", "okf_bundles_p6")
NEEDLES = ["环境空气污染物基本项目浓度限值", "年平均", "24 小时平均", "表1", "表2"]
NUM = re.compile(r"(PM2\.5|PM10|SO2|NO2|CO|O3)[^\n]{0,60}?\d")


def main() -> int:
    for tree in TREES:
        root = Path("/data/fagui_rag") / tree
        files = [p for p in root.rglob("*.md") if "3095" in p.name and "2026" in p.name]
        print("=" * 92)
        print("【%s】GB 3095—2026 相关 md：%d 份" % (tree, len(files)))
        for p in sorted(files)[:3]:
            t = io.open(p, encoding="utf-8", errors="replace").read()
            dead = t.count("![](images/")
            print("  · %s" % p.name[:76])
            print("      死链图片 %d 处 ｜ 字数 %d" % (dead, len(t)))
            for nd in NEEDLES:
                i = t.find(nd)
                if i >= 0:
                    seg = re.sub(r"\s+", " ", t[max(0, i - 60):i + 260])
                    print("      [%s] …%s…" % (nd, seg))
                    break
            hits = NUM.findall(t)
            print("      含「污染物+数字」的行片段 %d 处；示例：%s"
                  % (len(hits), hits[:6]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
