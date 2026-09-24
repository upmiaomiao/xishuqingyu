#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复现 C5：环氧树脂项目被匹配到「学校、福利院、养老院（建筑面积5000平方米及以上的）」。

用户反馈原文：「环氧树脂项目匹配到"学校、福利院、养老院（5000㎡及以上）"。
把"5000 吨"误匹配为"5000 平方米"，纯字符串匹配不理解行业。」

本脚本不猜：直接用真实判据库跑 `Criteria.find_items`（审核线与生成线共用同一段），
把 top5 打分与"为什么命中"打出来；同时统计判据库里**有多少条目的"行业代码"
其实是从阈值数字里抠出来的**（这是根因的爆炸半径）。

用法：python 复现_C5名录错配.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))            # 过程脚本/
ROOT = os.path.dirname(HERE)                                 # 审核智能体/（audit 包在这一层）
sys.path.insert(0, ROOT)
CRIT = os.path.join(os.path.dirname(os.path.dirname(ROOT)), "判据库")   # 0911训练/判据库
os.environ.setdefault("EIA_CRITERIA_DIR", CRIT)

from audit.criteria import Criteria, UNIT_FACTOR                    # noqa: E402

UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNIT_FACTOR), key=len, reverse=True))
# 中文量词：不是 UNIT_FACTOR 里的单位，但同样不该被当成行业代码
EXTRA = "人|张|床|个|所|座|辆|艘|条|亿|万|年|月|日"
UNITISH = re.compile(r"^\s*(?:%s|%s)" % (UNIT_ALT, EXTRA))

QUERIES = {
    "① 环氧树脂（用户反馈的错例）":
        "年产5000吨环氧树脂项目 合成材料制造 265 环氧树脂 5000吨/年 环氧氯丙烷 双酚A",
    "② 环氧树脂（没填行业类别，只有名称与产能）":
        "年产5000吨环氧树脂项目 环氧树脂 5000吨/年",
    "③ 学校项目（对照组：**应该**命中 110）":
        "新建学校项目 建筑面积6000平方米 教学楼 中学",
    "④ 生物质发电（对照组：应命中 89）":
        "生物质能发电 D4417 生活垃圾发电 报告书",
    "⑤ 玻璃（对照组：应命中 57）":
        "玻璃制造 304 其他玻璃制造 年产18万吨建筑节能玻璃",
    "⑥ 锅炉（对照组：应命中 91）":
        "热力生产和供应工程 燃煤锅炉 65吨/小时",
}


def unit_bound(cat: str) -> list:
    """条目里"长得像行业代码、其实是阈值数字"的数字（跟单位绑在一起）。"""
    bad = []
    for m in re.finditer(r"(\d{3,4})", cat):
        if UNITISH.match(cat[m.end():m.end() + 8]):
            bad.append(m.group(1))
    return bad


def main() -> int:
    C = Criteria(CRIT)
    print("判据库：%s" % CRIT)
    print("名录条目 %d 条\n" % len(C.catalog))

    # ---- 爆炸半径：哪些条目的 _codes 是从阈值数字里抠出来的 ----
    buggy = []
    for it in C.catalog:
        bad = unit_bound(it.get("category", ""))
        if bad:
            buggy.append((it["no"], it["category"], bad, it["_codes"]))
    print("=" * 96)
    print("【根因统计】条目名里的阈值数字被当成「行业代码」的条目：%d 条" % len(buggy))
    for no, cat, bad, codes in buggy:
        print("  序号%-4s %-44s 阈值数字%s → _codes=%s" % (no, cat[:44], bad, codes))
    print("  （这类条目只要查询串里出现同一个数字就会 +60 分，而最低门槛只有 16 分）")

    # ---- 逐题看 top5 ----
    for name, q in QUERIES.items():
        print("\n" + "=" * 96)
        print("%s\n  查询串：%s" % (name, q))
        items = C.find_items(q, top=5)
        print("  打分 top5：")
        for s, no, cat, why in C._last_scores:
            print("    %5d 分  序号%-4s %-40s 命中：%s" % (s, no, cat, why[:6]))
        print("  返回条目：%s" % [(it["no"], it["category"][:30]) for it in items])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
