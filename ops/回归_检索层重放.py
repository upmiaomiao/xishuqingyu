#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器侧：只重放**检索**（不调模型），用于检索层 A/B。

为什么要 A/B 而不是跟 09-21 的老基线比：
  09-21 的实跑基线是在**旧索引**上录的；09-22 索引做过"标题修正 + 状态改写"重建
  （标题进了嵌入配方，会合法地改变检索结果）。拿它当基线，等于把索引变更的账
  算到检索器改动头上 —— 实测 20 条全变，其中 14 条和标准号毫无关系，就是这个偏差。
  正确的零回归判据必须在**同一索引、同一进程外**只切一个开关：
     RAG_STD_PIN=0  → 关掉"标准号硬命中"，等价于改动前行为
     RAG_STD_PIN=1  → 打开（线上默认）
  两边跑同一批题，题面不含标准号的必须逐条完全一致。

用法（服务器）：
  RAG_STD_PIN=0 /home/test/fagui_serve/.venv/bin/python 回归_检索层重放.py off
  RAG_STD_PIN=1 /home/test/fagui_serve/.venv/bin/python 回归_检索层重放.py on
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, "/data/fagui_rag")
sys.path.insert(0, "/home/test/xishu_qingyu_serve")

from xishu_pipeline.retrieve import retriever                      # noqa: E402
import retriever as R                                               # noqa: E402

ARM = sys.argv[1] if len(sys.argv) > 1 else "on"
QS = json.load(open("/home/test/回归_检索层_题目.json", encoding="utf-8"))
print("臂：%s ｜ STD_PIN_ON=%s POOL=%s FINAL=%s"
      % (ARM, R.STD_PIN_ON, R.STD_PIN_POOL, R.STD_PIN_FINAL))

out = []
t0 = time.time()
for i, item in enumerate(QS, 1):
    q = item["q"]
    try:
        hits = retriever.retrieve(q, 20, 5)
        now = [(h.get("title") or h.get("source") or "").strip() for h in hits]
    except Exception as exc:                                        # noqa: BLE001
        now = []
        print("  [%02d] 失败：%s（%s）" % (i, q[:36], exc))
    out.append({"q": q, "has_code": item.get("has_code"), "now": now})
    print("  [%02d] %-44s → %s" % (i, q[:44], " ｜ ".join(x[:24] for x in now[:3])))
path = "/home/test/回归_检索层_结果_%s.json" % ARM
json.dump(out, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("完成 %d 条，用时 %.1f 分钟 → %s" % (len(out), (time.time() - t0) / 60, path))
