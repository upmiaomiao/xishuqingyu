#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按去重清单删除 okf_bundles 里的重复副本 md（**先备份、留回滚清单**）。

用法：
  python 执行去重.py            # 预演：只核对，不删
  python 执行去重.py --apply    # 真删，并写 /tmp/dedup_deleted.json 供回滚
"""
from __future__ import annotations

import json
import os
import sys

BUNDLE = "/data/fagui_rag/okf_bundles"
PLAN = "/tmp/dedup_plan.json"
DELETED = "/tmp/dedup_deleted.json"
APPLY = "--apply" in sys.argv

plan = json.load(open(PLAN, encoding="utf-8"))
drop = plan["drop"]
print(f"清单：待删 {len(drop)} 份（来自 {plan['dup_groups']} 组重复）")

missing, ok = [], []
for d in drop:
    p = os.path.join(BUNDLE, d["source"])
    if os.path.isfile(p):
        ok.append((p, os.path.getsize(p), d))
    else:
        missing.append(d["source"])

print(f"  文件存在 {len(ok)}，缺失 {len(missing)}")
if missing:
    for m in missing[:5]:
        print("   缺失:", m)
    sys.exit("有缺失文件，清单与 bundles 不一致，终止")

total_mb = sum(s for _, s, _ in ok) / 1024 / 1024
print(f"  合计 {total_mb:.1f} MB")

if not APPLY:
    print("\n（预演，未删除任何文件）")
    sys.exit(0)

# 记录回滚清单（含备份目录，便于一条命令恢复）
json.dump({"bundle_root": BUNDLE, "backup": "/data/fagui_rag/okf_bundles.bak_before_dedup_20260916",
           "deleted": [{"path": p, "size": s, "kept": d["keep"], "hash": d["hash"]}
                       for p, s, d in ok]},
          open(DELETED, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

n = 0
for p, _s, _d in ok:
    os.remove(p)
    n += 1
print(f"\n已删除 {n} 份；回滚清单：{DELETED}")
print("回滚：cp -r okf_bundles.bak_before_dedup_20260916/. okf_bundles/ && 重建索引")
