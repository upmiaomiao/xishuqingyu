#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 `_审核结果/` 里**不再对应任何当前报告**的旧结果归档到 `_历史/`。

为什么需要：报告改名/去重后，旧结果文件会留在结果目录里。它会被导出、被 gold 评测
当成"另一份报告"，出现"同一份报告两项结论""项数不是 18"这类怪现象。
按项目纪律：**归档不删除**，只移走。

用法：python 归档_过期结果.py [--apply]
"""
from __future__ import annotations

import glob
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit.runner import list_reports  # noqa: E402


def main():
    apply = "--apply" in sys.argv
    result_dir = os.environ.get("AUDIT_RESULT_DIR") or os.path.join(HERE, "_审核结果")
    hist = os.path.join(result_dir, "_历史")
    stems = {n.rsplit(".", 1)[0] for n in list_reports()}
    moved = []
    for p in sorted(glob.glob(os.path.join(result_dir, "*.json"))):
        stem = os.path.basename(p)[:-5]
        if stem in stems or stem.startswith("gold评测"):
            continue
        moved.append(p)
    print(f"结果目录：{result_dir}")
    print(f"当前报告 {len(stems)} 份；需归档的旧结果 {len(moved)} 个：")
    for p in moved:
        print("   -", os.path.basename(p))
    if not moved:
        return 0
    if not apply:
        print("（未加 --apply，仅预览）")
        return 0
    os.makedirs(hist, exist_ok=True)
    for p in moved:
        shutil.move(p, os.path.join(hist, os.path.basename(p)))
    print(f"已归档到 {hist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())