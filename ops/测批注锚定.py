# -*- coding: utf-8 -*-
"""批注锚定层自测（**只读**：不写站点、不写索引、不落任何产物）。

跑法：把 audit_anchor.py 放到 /home/test/_stage/ 后
     /home/test/fagui_serve/.venv/bin/python /home/test/测批注锚定.py
"""
import glob
import json
import os
import sys
import time

sys.path.insert(0, "/home/test/_stage")          # 待验证的新模块（尚未上线）
sys.path.insert(0, "/data/eia_audit")

from audit_anchor import (LEVEL_EXACT, LEVEL_NEAR, LEVEL_NONE,  # noqa: E402
                          LEVEL_PAGE, annot_stats, build_anchors, load_parsed,
                          page_payload)

RES = "/data/eia_audit/_审核结果"
REPORTS = "/data/eia_reports"

fails = []
tot = {LEVEL_EXACT: 0, LEVEL_NEAR: 0, LEVEL_PAGE: 0, LEVEL_NONE: 0}

for jf in sorted(glob.glob(os.path.join(RES, "*.json"))):
    base = os.path.basename(jf)
    if base == "gold评测.json":
        continue
    res = json.load(open(jf, encoding="utf-8"))
    name = res["file"]["name"]
    pdf = os.path.join(REPORTS, name)
    print("=" * 96)
    print("报告：", name, " 页数：", res["file"].get("pages"), " 存在：", os.path.isfile(pdf))
    if not os.path.isfile(pdf):
        fails.append("缺 PDF：" + name)
        continue

    t0 = time.time()
    parsed = load_parsed(name, pdf, allow_parse=False)
    t1 = time.time()
    anchors = build_anchors(res, parsed)
    st = annot_stats(anchors)
    for k in tot:
        tot[k] += st.get(k, 0)
    print("  解析缓存读取 %.2fs；批注 %d 条；定位：精确 %d / 近似 %d / 仅页码 %d / 无证据 %d"
          % (t1 - t0, st["合计"], st[LEVEL_EXACT], st[LEVEL_NEAR],
             st[LEVEL_PAGE], st[LEVEL_NONE]))

    # 断言 1：页码必须落在报告范围内；无证据条目不得带页码/摘录
    for a in anchors:
        if a["page"] is not None and not (1 <= a["page"] <= parsed["pages"]):
            fails.append("%s 页码越界：%s P%s" % (name, a["审核项"], a["page"]))
        if a["span"]:
            t = parsed["page_text"][a["page"] - 1]
            s, e = a["span"]
            if not (0 <= s < e <= len(t)):
                fails.append("%s 字符区间越界：%s P%s %s" % (name, a["审核项"], a["page"], a["span"]))
        if a["level"] == LEVEL_NONE and (a["page"] or a["quote"]):
            fails.append("%s 无证据条目却带了页码/摘录：%s" % (name, a["审核项"]))
        if a["level"] != LEVEL_NONE and a["page"] is None:
            fails.append("%s 有证据却没有页码：%s" % (name, a["审核项"]))

    # 断言 2：每页取回来必须自洽（首/中/尾三页抽检）
    for pno in (1, max(1, parsed["pages"] // 2), parsed["pages"]):
        pay = page_payload(parsed, pno)
        if pay["n"] != pno or pay["total"] != parsed["pages"]:
            fails.append("%s 页负载不对：%s" % (name, pno))
        if not pay["empty"] and not pay["text"].strip():
            fails.append("%s 非空页却没有正文：%s" % (name, pno))

    # 抽样展示：每档各两条，人工看一眼判得对不对
    for lv in (LEVEL_EXACT, LEVEL_NEAR, LEVEL_PAGE):
        got = [a for a in anchors if a["level"] == lv][:2]
        for a in got:
            print("   [%s] %s P%s(印%s) 「%s」" %
                  (lv, a["审核项"], a["page"], a["printed"], (a["quote"] or "")[:38]))
            print("          %s" % a["why"])
            if a["span"]:
                s, e = a["span"]
                t = parsed["page_text"][a["page"] - 1]
                print("          原文：…%s…" % t[max(0, s - 18):e + 18].replace("\n", "⏎"))

print()
print("=" * 96)
print("合计：", tot, " 总批注", sum(tot.values()))
if fails:
    print("❌ 失败 %d 条：" % len(fails))
    for f in fails[:20]:
        print("   ", f)
    sys.exit(1)
print("✅ 全部断言通过（页码范围 / 字符区间 / 页负载）")
