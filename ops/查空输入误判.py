# -*- coding: utf-8 -*-
"""影响面分析：把"判据输入为空却判符合要求"这个坑修掉之后，会影响哪些结论。

用户反馈的那条（环境风险专项设置判"无问题"）背后是一类 bug：
判据函数在**输入列表为空**时把"没有证据"当成了"判定为否"。
先数清楚有哪几处、会影响多少条结论 —— 这决定改动值不值得做。
"""
import json
import os

RD = "/data/eia_audit/_审核结果"
WATCH = ("大气专项评价设置", "环境风险专项评价设置", "地表水专项评价设置",
         "地下水专项评价设置", "生态专项评价设置", "海洋专项评价设置")
EMPTY_KEYS = {"废气污染物清单", "危险物质清单"}

files = [f for f in sorted(os.listdir(RD)) if f.endswith(".json")
         and not f.startswith("_") and os.path.isfile(os.path.join(RD, f))]

print("%-34s %-22s %-8s %s" % ("报告", "审核项", "结论", "判据输入/理由"))
print("-" * 118)
suspect = []
for fn in files:
    try:
        j = json.load(open(os.path.join(RD, fn), encoding="utf-8"))
    except Exception:
        continue
    for it in (j.get("items") or []):
        nm = it.get("审核项") or ""
        if nm not in WATCH:
            continue
        tr = it.get("判据轨迹") or {}
        r = tr.get("判据结论") or {}
        inp = tr.get("判据输入") or {}
        empty = [k for k in EMPTY_KEYS if k in inp and not inp[k]]
        verdict = it.get("AI审核")
        note = ""
        if r.get("status") == "decided" and verdict in ("无问题", "优化调整建议") and empty:
            note = "← 输入为空却判『%s』（%.0f 字理由：%s）" % (
                verdict, len(it.get("理由") or ""), (it.get("理由") or "")[:46])
            suspect.append((fn, nm, empty))
        print("%-34s %-22s %-8s %s%s" % (
            fn.replace(".json", "")[:32], nm, verdict,
            ("空输入=" + ",".join(empty)) if empty else ("status=" + str(r.get("status"))), note))

print("\n=== 判定：输入列表为空、却给出『符合要求』类结论的条数 = %d ===" % len(suspect))
for fn, nm, empty in suspect:
    print("   %s / %s（空：%s）" % (fn.replace(".json", "")[:28], nm, ",".join(empty)))
