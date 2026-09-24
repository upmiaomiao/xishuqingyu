#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器侧判据库自检：别名表/表B.1/名录条目数，以及几个易错名称的解析结果。

为什么要有这个脚本：判据库在服务器上是 `/data/fagui_rag/criteria`，
本地改了判据必须**同步过去**，否则审核结论会不一致（实测踩过：别名表没同步，
同一个物质在本地能对上、在服务器上"表B.1 未列"）。
"""
import os
import sys

sys.path.insert(0, "/data/eia_audit")
from audit.criteria import DEFAULT_DIR, Criteria  # noqa: E402


def main():
    C = Criteria()
    risk = C.risk
    print("判据目录:", DEFAULT_DIR, os.path.isdir(DEFAULT_DIR))
    print("名录条目:", len(C.catalog))
    print("表B.1 物质:", len(risk.get("substances", [])))
    print("别名条数:", len(risk.get("aliases") or {}))
    print("别名表版本标记:", risk.get("aliases_note", "（无 —— 说明服务器判据是旧的）")[:60])
    for n in ("CO", "HCl", "NO", "H2S", "NH3", "轻柴油", "二噁英", "CODCr 浓度≥10000mg/L 的有机废液"):
        s = C.substance_threshold(n)
        print("   %-30s -> %s" % (n, (s["name"], s["threshold_t"]) if s else None))
    return 0


if __name__ == "__main__":
    sys.exit(main())