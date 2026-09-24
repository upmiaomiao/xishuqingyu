#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告审核智能体 · 命令行入口。

用法：
  python 审核_报告.py "1、环评报告.pdf"          # 单份，含模型抽取
  python 审核_报告.py --no-llm --all            # 全部（跳过重复件），只用表/正则
  python 审核_报告.py --list                    # 列出报告目录里的文件
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit.criteria import Criteria            # noqa: E402
from audit.runner import (audit_file, cache_dir, list_reports,  # noqa: E402
                          print_result, report_dir)

OUT = os.path.join(HERE, "_审核结果")


def main():
    args = sys.argv[1:]
    use_llm = "--no-llm" not in args
    do_all = "--all" in args
    args = [a for a in args if not a.startswith("--")]
    C = Criteria()
    root = report_dir()
    if "--list" in sys.argv:
        for n in list_reports():
            print(n)
        return 0
    names = list_reports() if do_all else (args or ["1、环评报告.pdf"])
    os.makedirs(OUT, exist_ok=True)
    results = []
    for n in names:
        p = n if os.path.isabs(n) else os.path.join(root, n)
        if not os.path.exists(p):
            print(f"[跳过] 不存在：{p}")
            continue
        r = audit_file(p, use_llm=use_llm, verbose=True, C=C)
        results.append(r)
        if use_llm:
            print_result(r)
        else:
            print_result(r)
        safe = os.path.splitext(os.path.basename(n))[0][:40].replace("/", "_")
        with open(os.path.join(OUT, f"{safe}.json"), "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
    print(f"\n==== 共 {len(results)} 份，结果已写入 {OUT}（解析缓存 {cache_dir()}）====")
    for r in results:
        print(f"  {r['file']['name'][:44]:46s} {r['统计']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())