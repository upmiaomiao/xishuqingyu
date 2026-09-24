# -*- coding: utf-8 -*-
"""看审核结果 JSON 长什么样：结构、统计、逐条字段、证据页码/摘录质量。只读。"""
import glob
import json
import os
import statistics

D = "/data/eia_audit/_审核结果"


def brief(x, n=160):
    s = x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)
    s = s.replace("\n", "⏎")
    return s[:n] + ("…" if len(s) > n else "")


files = sorted(glob.glob(os.path.join(D, "*.json")))
print("结果文件：", [os.path.basename(f) for f in files])
print()

for f in files:
    if os.path.basename(f) in ("gold评测.json",):
        continue
    d = json.load(open(f, encoding="utf-8"))
    items = d.get("items", [])
    print("=" * 100)
    print("文件：", os.path.basename(f))
    print("顶层键：", list(d.keys()))
    print("file 键：", list((d.get("file") or {}).keys()) if isinstance(d.get("file"), dict) else d.get("file"))
    print("统计：", json.dumps(d.get("统计"), ensure_ascii=False))
    print("items：", len(items))
    if not items:
        continue
    print("item 键：", list(items[0].keys()))
    # 证据质量
    pages = [len(it.get("证据") or []) for it in items]
    qlen = [len(str(e.get("quote") or "")) for it in items for e in (it.get("证据") or [])]
    nopage = sum(1 for it in items for e in (it.get("证据") or []) if not e.get("page"))
    print("每条证据数：min=%d max=%d 平均=%.1f；证据总数=%d；缺页码=%d" %
          (min(pages), max(pages), sum(pages) / len(pages), sum(pages), nopage))
    if qlen:
        print("摘录长度：min=%d 中位=%d max=%d" %
              (min(qlen), int(statistics.median(qlen)), max(qlen)))
    print("类别分布：", {})
    from collections import Counter
    print("  类别：", Counter(it.get("类别", "") for it in items).most_common())
    print("  结论：", Counter(it.get("AI审核", "") for it in items).most_common())
    print("  置信度：", Counter(str(it.get("置信度", "")) for it in items).most_common())
    print("  审核项样例：", [it.get("审核项") for it in items[:4]])
    print()
    for it in items[:2]:
        print("  --- 样例条目 ---")
        for k, v in it.items():
            print("    %-8s %s" % (k, brief(v, 220)))
    print()
