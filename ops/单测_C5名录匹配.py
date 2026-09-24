#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C5 名录匹配专项单测（防复发）。

用户反馈原话：「环氧树脂项目匹配到"学校、福利院、养老院（5000㎡及以上）"。
把"5000 吨"误匹配为"5000 平方米"，纯字符串匹配不理解行业。需按行业代码+工艺结构化查询。」

根因（2026-09-22 定位）：条目行业代码用 `re.findall(r"(\\d{3,4})")` 提取，
于是「学校、福利院、养老院（建筑面积**5000**平方米及以上的）」的**面积阈值 5000**
被当成行业代码；查询串里只要出现「年产**5000**吨」，数字一撞就 +60 分，而门槛只有 16 分。

本单测覆盖三件事：
  1. 全库不再有"阈值数字被当行业代码"的条目（数据层不变量）；
  2. 用户那道错例不再误配（环氧树脂 → 不得命中 110/111），且**宁可不给也不猜**；
  3. 正例仍能命中：学校→110、批发市场→111、既有对照（玻璃 57／生物质 89／胶粘剂 53）不回归。

用法：python 单测_C5名录匹配.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 单测/
BASE = os.path.dirname(HERE)                               # 审核智能体/（本地）或 /（服务器）
# 引擎包目录：本地就是 BASE；服务器上传到 /home/test 时用 EIA_ENGINE_DIR=/data/eia_audit 指过去
ENGINE = os.environ.get("EIA_ENGINE_DIR") or BASE
sys.path.insert(0, ENGINE)
from audit.criteria import (Criteria, UNIT_FACTOR, industry_codes,   # noqa: E402
                            code_in_query, lead_name_tokens)

ROOT = os.path.dirname(os.path.dirname(BASE))              # 0911训练/
# 判据目录：优先环境变量（服务器上是 /data/fagui_rag/criteria），本地回落到 0911训练/判据库
CRIT = os.environ.get("EIA_CRITERIA_DIR") or os.path.join(ROOT, "判据库")
os.environ.setdefault("EIA_CRITERIA_DIR", CRIT)

PASS, FAIL = [], []


def check(name, got, want):
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  [{'✓' if ok else ''}] {name}: got={got!r} want={want!r}")


UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNIT_FACTOR), key=len, reverse=True))
UNITISH = re.compile(r"^\s*(?:%s|人|张|床|个|所|座|辆|艘|条|亿|万|年|月|日)" % UNIT_ALT)

C = Criteria(CRIT)


def first_no(q):
    items = C.find_items(q, top=5)
    return items[0]["no"] if items else None


def nos(q):
    return [it["no"] for it in C.find_items(q, top=5)]


def main() -> int:
    print("判据库：%s（名录 %d 条）\n" % (CRIT, len(C.catalog)))

    print("[1] 数据层不变量：行业代码里不得混入阈值数字")
    bad = []
    for it in C.catalog:
        cat = it.get("category", "") or ""
        for m in re.finditer(r"(?<!\d)(\d{3,4})(?!\d)", cat):
            if UNITISH.match(cat[m.end():m.end() + 8]) and m.group(1) in it["_codes"]:
                bad.append((it["no"], cat[:24], m.group(1)))
    check("阈值数字被当行业代码的条目数", len(bad), 0)
    check("110 学校条目的 _codes 为空", C.catalog and
          [it for it in C.catalog if it["no"] == 110][0]["_codes"], [])
    check("110 名称部分（供凭名字命中）",
          [it for it in C.catalog if it["no"] == 110][0]["_lead_tokens"],
          ["学校", "福利院", "养老院"])

    print("\n[2] 反向保护：查询串里只有「5000 吨」不算行业代码命中")
    check("code_in_query('5000','年产5000吨')", code_in_query("5000", "年产5000吨环氧树脂"), False)
    check("code_in_query('265','合成材料制造 265')", code_in_query("265", "合成材料制造 265"), True)

    print("\n[3] 用户错例：环氧树脂项目不得命中 110/111（宁可不给也不猜）")
    q1 = "年产5000吨环氧树脂项目 合成材料制造 265 环氧树脂 5000吨/年 环氧氯丙烷 双酚A"
    q2 = "年产5000吨环氧树脂项目 环氧树脂 5000吨/年"
    check("① 填了行业类别 → 首位为 44（化学原料和化学制品制造业）", first_no(q1), 44)
    check("① 候选中不含 110", 110 in nos(q1), False)
    check("① 候选中不含 111", 111 in nos(q1), False)
    check("② 只填名称与产能 → 不返回任何条目（不猜）", nos(q2), [])

    print("\n[4] 正例仍应命中（修数字撞号后靠名字命中）")
    check("学校项目 → 110", first_no("新建学校项目 建筑面积6000平方米 教学楼 中学"), 110)
    check("批发市场项目 → 111", first_no("新建批发市场项目 营业面积8000平方米"), 111)
    check("既有对照：玻璃 → 57", first_no("玻璃制造 304 其他玻璃制造 年产18万吨建筑节能玻璃"), 57)
    check("既有对照：生物质发电 → 89", first_no("生物质能发电 D4417 生活垃圾发电 报告书"), 89)
    check("既有对照：胶粘剂 → 53",
          first_no("塑料制品业 塑料零件及其他塑料制品制造 聚氨酯胶水 乙酸乙酯 溶剂型"), 53)

    print("\n==== 通过 %d / 失败 %d ====" % (len(PASS), len(FAIL)))
    if FAIL:
        print("失败项：" + "；".join(FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
