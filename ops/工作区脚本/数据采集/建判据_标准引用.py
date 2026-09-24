#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从语料报告里机械抽取"被引用的标准"，建成 判据库/标准引用清单.json。

为什么这么做：判据库里**没有**"行业→适用标准"清单，报告生成时标准那一节只能留占位。
凭空写一份标准清单是编造；但语料里 7 份真实报告都各自列了适用标准 ——
把"哪份报告、哪一页、引了哪个标准、同一段落里在讲什么要素/污染物"抽出来，
就是一条**可追溯的事实**，可以给新项目做"候选标准"，再由人核定。

产物是**引用事实**，不是权威适用性判定 —— 这句话必须写进产物、也必须写进报告草稿。

用法：python 建判据_标准引用.py
"""
from __future__ import annotations

import collections
import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
WORK = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "审核智能体"))

from audit.runner import list_reports, report_dir  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

OUT = os.path.join(WORK, "判据库", "标准引用清单.json")
CACHE = os.path.join(ROOT, "审核智能体", "_cache")

# 标准号：GB/HJ/DB/GBZ/JGJ/CJJ 等 + 编号 + 年份（连字符有全角/半角/破折号多种写法）
STD_RX = re.compile(
    r"(?P<code>(?:GB|HJ|DB|GBZ|JGJ|CJJ|NY|AQ|SL|TD|MT|SH|JB)\s*/?\s*(?:T|Z)?\s*\d{2,5})"
    r"\s*[—\-－–~]\s*(?P<year>\d{4})")
NAME_RX = re.compile(r"《([^》]{4,40})》")

# 共现词表：要素 + 常见污染物（用来判断这个标准"在这一段里管什么"）
ELEMENTS = ["废气", "废水", "噪声", "固体废物", "固废", "地下水", "土壤", "环境空气",
            "地表水", "声环境", "环境风险", "地表水环境", "生态", "恶臭", "振动"]
POLLUTANTS = ["颗粒物", "二氧化硫", "氮氧化物", "氯化氢", "氟化物", "二噁英", "氨", "硫化氢",
              "非甲烷总烃", "VOCs", "挥发性有机物", "甲苯", "二甲苯", "甲醛", "铅", "汞", "",
              "砷", "铬", "镍", "铜", "锌", "COD", "CODCr", "BOD5", "氨氮", "总磷", "总氮",
              "石油类", "悬浮物", "pH", "色度", "粪大肠菌群", "总大肠菌群", "臭气浓度",
              "甲烷", "氯气", "氰化物", "苯并[a]芘"]
CTX = 240            # 共现取多大的上下文窗口


def norm(m: re.Match) -> str:
    code = re.sub(r"\s+", "", m.group("code")).upper()
    return f"{code}-{m.group('year')}"


def main():
    rows = collections.defaultdict(lambda: {
        "标准号": "", "名称": "", "引用报告数": 0, "引用次数": 0,
        "共现要素": collections.Counter(), "共现污染物": collections.Counter(),
        "出处": []})
    reports = list_reports()
    print("扫描 %d 份报告…" % len(reports))
    for name in reports:
        path = os.path.join(report_dir(), name)
        rep = load_or_parse(path, cache_dir=CACHE)
        seen_here = set()
        for page, text in enumerate(rep.page_text, 1):
            flat = re.sub(r"\s+", " ", text)
            for m in STD_RX.finditer(flat):
                key = norm(m)
                r = rows[key]
                r["标准号"] = key
                r["引用次数"] += 1
                seen_here.add(key)
                a, b = max(0, m.start() - CTX), min(len(flat), m.end() + CTX)
                win = flat[a:b]
                for w in ELEMENTS:
                    if w in win:
                        r["共现要素"][w] += 1
                for w in POLLUTANTS:
                    if w in win:
                        r["共现污染物"][w] += 1
                if not r["名称"]:
                    # 名称必须**紧邻**标准号，否则会串到相邻标准上去 —— 实测：
                    # 「《地表水环境质量标准》（GB 3838-2002）、《建设项目环境风险评价技术导则》
                    #   （HJ 169-2018）」里，宽松取"前面最近的《》"会把 HJ169 配成"地表水环境质量标准"。
                    # **错名字比没名字更糟**，所以只在「《名称》」紧接标准号时才认，否则留空。
                    pre = flat[max(0, m.start() - 60): m.start()]
                    nm = re.search(r"《([^》]{4,40})》\s*[（(]?\s*$", pre)
                    if nm:
                        cand = nm.group(1)
                        if any(k in cand for k in ("标准", "规范", "技术要求", "导则", "指南")):
                            r["名称"] = cand
                if len(r["出处"]) < 3:
                    r["出处"].append({"报告": name, "页码": page,
                                      "原文": flat[max(0, m.start() - 60): m.end() + 40]})
        for k in seen_here:
            rows[k]["引用报告数"] += 1

    out = {
        "来源": {"语料目录": report_dir(), "报告数": len(reports)},
        "性质": "**引用事实**：这些标准是从 7 份真实报告里抽出来的、各报告自己列过的标准。"
                "它不是权威的『行业→适用标准』判定，不能直接当作新项目的适用标准；"
                "生成稿里只能作为**候选**列出，并注明来自语料引用、须人工核定。",
        "标准数": len(rows),
        "标准": [],
        "生成": {"脚本": os.path.basename(__file__),
                 "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    }
    for key, r in sorted(rows.items(), key=lambda kv: (-kv[1]["引用报告数"], -kv[1]["引用次数"], kv[0])):
        out["标准"].append({
            "标准号": r["标准号"], "名称": r["名称"],
            "引用报告数": r["引用报告数"], "引用次数": r["引用次数"],
            "共现要素": [k for k, _ in r["共现要素"].most_common(4)],
            "共现污染物": [k for k, _ in r["共现污染物"].most_common(6)],
            "出处": r["出处"],
        })
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("已写出：", OUT)
    print("标准 %d 个；被 2 份以上报告引用（可视为常用）的：" % len(out["标准"]))
    for s in out["标准"]:
        if s["引用报告数"] >= 2:
            print("  %-16s %-28s 引用 %d 份/共 %d 次  共现：%s"
                  % (s["标准号"], (s["名称"] or "")[:26], s["引用报告数"], s["引用次数"],
                     "、".join((s["共现要素"] + s["共现污染物"])[:5])))
    return 0


if __name__ == "__main__":
    sys.exit(main())