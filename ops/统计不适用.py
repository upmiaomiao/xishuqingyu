# -*- coding: utf-8 -*-
"""统计"不适用"到底是哪些情况 —— 用已落盘的 6 份审核结果，按理由归类。

用户问：「报告审核里面不适用，这个不适用主要指什么情况？」
与其解释，不如把实际结果统计出来。
"""
import json
import os
import re

RD = "/data/eia_audit/_审核结果"
files = [f for f in sorted(os.listdir(RD)) if f.endswith(".json")
         and not f.startswith("_") and os.path.isfile(os.path.join(RD, f))]

groups = {}
per_item = {}
n_files = 0
for fn in files:
    try:
        j = json.load(open(os.path.join(RD, fn), encoding="utf-8"))
    except Exception as e:
        print("跳过 %s：%s" % (fn, e))
        continue
    items = j.get("items") or []
    if not items:
        continue
    n_files += 1
    for it in items:
        if (it.get("AI审核") or "") != "不适用":
            continue
        name = it.get("审核项") or "?"
        why = (it.get("理由") or "").strip()
        per_item[name] = per_item.get(name, 0) + 1
        # 归类
        if "仅针对" in why and "报告表" in why:
            k = "① 本项只针对《报告表编制技术指南（污染影响类）》适用对象，本报告是报告书"
        elif re.search(r"报告表|不适用该", why) and "报告表" in why:
            k = "① 本项只针对《报告表编制技术指南（污染影响类）》适用对象，本报告是报告书"
        elif "不开展专项评价" in why or "表1 正文明确" in why:
            k = "② 导则表1 正文明确该要素『不开展』专项评价"
        elif "不涉及" in why or "不属于" in why or "不新增" in why or "非直接" in why:
            k = "③ 项目本身不涉及该要素（按判据机械判定为否）"
        else:
            k = "④ 其它：" + why[:40]
        groups.setdefault(k, []).append((fn[:18], name, why[:70]))

print("统计范围：%d 份有审核结果的报告\n" % n_files)
total = sum(len(v) for v in groups.values())
print("不适用共 %d 条，按原因分：\n" % total)
for k in sorted(groups):
    v = groups[k]
    print("%s —— %d 条" % (k, len(v)))
    for _, name, why in v[:3]:
        print("     · %s：%s" % (name, why))
    if len(v) > 3:
        print("     · …其余 %d 条同类" % (len(v) - 3))
print("\n哪些审核项最容易不适用：")
for name, c in sorted(per_item.items(), key=lambda x: -x[1]):
    print("   %-24s %d 次" % (name, c))
