#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核项 5-18（P3 新增）的**缺陷注入**测试。

做法：造一个最小的假报告对象（假 ParsedReport），把"报告里出错的样子"喂进去，
断言审核项**必须**报出该错误；再把"正确的样子"喂进去，断言**不能**误报。
不测"跑不跑得起来"，只测"错了能不能发现、对了会不会冤枉"。

跑法：python 单测_十八项.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（单测/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包在这里）
sys.path.insert(0, BASE)

from audit.criteria import Criteria                                   # noqa: E402
from audit.items_extra import (judge_completeness, judge_risk_potential,  # noqa: E402
                               judge_risk_q_calc, judge_risk_threshold,
                               judge_special_element, judge_special_quota,
                               judge_targets_table)
from audit.model import S_NA, S_OK, S_PROBLEM, S_SUSPECT              # noqa: E402

OK = FAIL = 0
FAILS = []


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
    else:
        FAIL += 1
        FAILS.append(f"{name} {extra}")
        print(f"  × {name} {extra}")


class FakeRep:
    """够用的假 ParsedReport：search() 的返回契约与 parse.ParsedReport 一致。"""

    def __init__(self, pages_text, tables=None, anchors=None, pdf="fake.pdf"):
        self.page_text = list(pages_text)
        self.pages = len(self.page_text)
        self.tables = tables or []
        self.anchors = anchors or {}
        self.pdf = pdf
        self.sha1 = "fake"

    def search(self, pattern, max_hits=5, ctx=0):
        out = []
        rx = re.compile(pattern)
        for i, t in enumerate(self.page_text, 1):
            for m in rx.finditer(t):
                a = max(0, m.start() - ctx)
                out.append({"page": i, "snippet": t[a:m.end() + ctx]})
                if len(out) >= max_hits:
                    return out
        return out


class FakeEx:
    def __init__(self, materials=None, basic=None, stated=None):
        self.risk_materials = materials or []
        self.basic = basic or {}
        self.special_stated = stated or {}
        self.special_inputs = {}


class Val:
    def __init__(self, value, page=1, quote=""):
        self.value = value
        self.page = page
        self.quote = quote or str(value)


C = Criteria()
print(f"判据库：名录 {len(C.catalog)} 条，风险物质 {len(C.risk.get('substances', []))} 条，"
      f"别名 {len(C.risk.get('aliases') or {})} 条")

# ---------------------------------------------------------------- 1. 风险物质别名与防误匹配
print("\n[1] 风险物质名称匹配（别名表 + 防子串误匹配）")
cases = [("CO", "一氧化碳", 7.5), ("HCl", "氯化氢", 2.5), ("NO", "一氧化氮", 0.5),
         ("H2S", "硫化氢", 2.5), ("NH3", "氨气", 5.0), ("SO2", "二氧化硫", 2.5),
         ("轻柴油", "油类物质", 2500.0), ("柴油", "油类物质", 2500.0)]
for q, want_name, want_t in cases:
    s = C.substance_threshold(q)
    check(f"别名 {q} → {want_name}", bool(s) and want_name in s["name"] and s["threshold_t"] == want_t,
          f"实际={s and (s['name'], s['threshold_t'])}")
# 这四条是"必须拒绝"的：子串误匹配会直接造出假结论
for q in ("CO", "NH3", "氨", "Cr"):
    s = C.substance_threshold(q)
    bad = s and ("CODCr" in s["name"] or "氨基异丁烷" in s["name"] or "氨水" in s["name"])
    check(f"不得误匹配 {q}", not bad, f"实际={s and s['name']}")
check("未列物质 二噁英 应查不到", C.substance_threshold("二噁英") is None)

# ---------------------------------------------------------------- 2. 临界量引用正确性
print("\n[2] 风险物质临界量引用正确性（报告写错 ↔ 必须报出）")
good = [{"名称": "CO", "临界量t": 7.5, "最大贮存量t": None, "页码": 3,
         "原文": "CO | 随烟气排放 | — | 7.5 | —"}]
bad = [{"名称": "CO", "临界量t": 1.5, "最大贮存量t": None, "页码": 3,
        "原文": "CO | 随烟气排放 | — | 1.5 | —"}]
it = judge_risk_threshold(FakeRep(["", "", ""]), FakeEx(materials=good), C)
check("临界量一致 → 无问题", it.AI审核 == S_OK, it.AI审核)
it = judge_risk_threshold(FakeRep(["", "", ""]), FakeEx(materials=bad), C)
check("临界量写错(1.5 vs 7.5) → 存在问题", it.AI审核 == S_PROBLEM, it.AI审核)
check("  写错时给出两个数值", "1.5" in it.理由 and "7.5" in it.理由, it.理由[:80])

# ---------------------------------------------------------------- 3. Q 值复算
print("\n[3] Q 值计算正确性（ΣQ 小于单项 ↔ 必须报出）")
mats = [{"名称": "轻柴油", "最大贮存量t": 80.0, "临界量t": 2500.0, "页码": 2,
         "原文": "7 | 轻柴油 | 柴油储罐 | 80 | 2500 | 0.032"}]
rep_bad = FakeRep(["", "表11.3-3 危险物质数量与临界量比值（Q）\nQ=0.014\n由表可知 Q＜1"])
it = judge_risk_q_calc(rep_bad, FakeEx(materials=mats), C, {})
check("Q=0.014 < 单项 0.032 → 存在问题", it.AI审核 == S_PROBLEM, it.AI审核)
check("  理由给出复算值", "0.032" in it.理由, it.理由[:90])
rep_good = FakeRep(["", "表11.3-3 危险物质数量与临界量比值（Q）\nQ=0.032\n由表可知 Q＜1"])
it = judge_risk_q_calc(rep_good, FakeEx(materials=mats), C, {})
check("Q=0.032 与复算一致 → 无问题", it.AI审核 == S_OK, it.AI审核)
rep_none = FakeRep(["", "表11.3-3 危险物质数量与临界量比值（Q）\n由表可知 Q＜1"])
it = judge_risk_q_calc(rep_none, FakeEx(materials=mats), C, {})
check("报告没给 Q → 疑似（不猜）", it.AI审核 == S_SUSPECT, it.AI审核)

# ---------------------------------------------------------------- 4. 潜势：ASCII 罗马数字
print("\n[4] 环境风险潜势（报告用 ASCII 的 I 也必须认得）")
rep_ascii = FakeRep(["", "由表11.3-3 可知，本项目Q＜1，因此，拟建项目环境风险潜势为I 级。"])
it = judge_risk_potential(rep_ascii, FakeEx(stated={}), C, "报告书")
check("ASCII「潜势为I」→ 无问题", it.AI审核 == S_OK, it.AI审核)
check("  识别为Ⅰ级", it.判据轨迹.get("报告自述潜势") == "Ⅰ", str(it.判据轨迹.get("报告自述潜势")))
rep_cn = FakeRep(["", "本项目环境风险潜势为Ⅰ级，Q＜1。"])
it = judge_risk_potential(rep_cn, FakeEx(stated={}), C, "报告书")
check("全角「潜势为Ⅰ级」→ 无问题", it.AI审核 == S_OK, it.AI审核)
rep_wrong = FakeRep(["", "本项目Q＜1，环境风险潜势为Ⅱ级。"])
it = judge_risk_potential(rep_wrong, FakeEx(stated={}), C, "报告书")
check("Q<1 却写Ⅱ级 → 疑似", it.AI审核 == S_SUSPECT, it.AI审核)
rep_none = FakeRep(["", "本项目开展了环境风险评价。"])
it = judge_risk_potential(rep_none, FakeEx(stated={}), C, "报告书")
check("没有潜势结论 → 疑似（不猜）", it.AI审核 == S_SUSPECT, it.AI审核)
it = judge_risk_potential(rep_ascii, FakeEx(stated={}), C, "报告表")
check("报告表未设环境风险专项 → 不适用", it.AI审核 == S_NA, it.AI审核)

# ---------------------------------------------------------------- 5. 生态：AND 短路
print("\n[5] 生态专项评价（AND 条件有一项为否即定论）")
prov = {}
rep = FakeRep(["", "本项目不新增河道取水。"])
merged = {"是否新增河道取水": False, "取水口下游500米内是否有重要水生生物三场一通道": None}
it = judge_special_element(rep, FakeEx(stated={}), C, merged, "生态", prov, "报告表")
check("不新增河道取水 → 无问题（不是疑似）", it.AI审核 == S_OK, it.AI审核)
merged2 = {"是否新增河道取水": None, "取水口下游500米内是否有重要水生生物三场一通道": None}
it = judge_special_element(rep, FakeEx(stated={}), C, merged2, "生态", prov, "报告表")
check("事实全缺 → 疑似", it.AI审核 == S_SUSPECT, it.AI审核)

# ---------------------------------------------------------------- 6. 海洋：按项目性质判定
print("\n[6] 海洋专项评价（按项目性质，不靠全文关键词）")
basic_inland = {"项目名称": Val("某某玻璃有限公司年产18万吨玻璃项目", 1, "项目名称：某某玻璃"),
                "行业类别": Val("玻璃制造 304", 1, "行业类别：玻璃制造")}
it = judge_special_element(FakeRep(["", "本项目为玻璃制造项目。"]),
                           FakeEx(basic=basic_inland, stated={}), C, {"是否直接向海排放污染物的海洋工程": None},
                           "海洋", prov, "报告表")
check("内陆项目 → 无问题", it.AI审核 == S_OK, it.AI审核)
basic_sea = {"项目名称": Val("某某港口码头工程", 1, "项目名称：某某港口码头工程"),
             "行业类别": Val("港口", 1, "行业类别：港口")}
it = judge_special_element(FakeRep(["", "本项目为港口码头工程。"]),
                           FakeEx(basic=basic_sea, stated={}), C, {"是否直接向海排放污染物的海洋工程": None},
                           "海洋", prov, "报告表")
check("港口项目 → 不得判无问题", it.AI审核 != S_OK, it.AI审核)

# ---------------------------------------------------------------- 7. 数量上限
print("\n[7] 专项评价数量上限")
it = judge_special_quota(FakeEx(stated={}), "报告书")
check("报告书 → 不适用", it.AI审核 == S_NA, it.AI审核)
it = judge_special_quota(FakeEx(stated={"大气": {"set": True}, "地表水": {"set": True},
                                        "地下水": {"set": True}}), "报告表")
check("3 项超上限 → 建议", it.AI审核 != S_OK, it.AI审核)
it = judge_special_quota(FakeEx(stated={"大气": {"set": True}}), "报告表")
check("1 项未超 → 无问题", it.AI审核 == S_OK, it.AI审核)

# ---------------------------------------------------------------- 8. 保护目标表
print("\n[8] 环境保护目标表完整性")
tbl_ok = [{"page": 20, "rows": [["序号", "名称", "方位", "距离", "户数", "人数"],
                                ["1", "刘家峪村", "E", "303.9", "142", "390"]]}]
it = judge_targets_table(FakeRep(["", ""], tables=tbl_ok), FakeEx())
check("有方位/距离且有数据行 → 无问题", it.AI审核 == S_OK, it.AI审核)
tbl_no_pos = [{"page": 20, "rows": [["序号", "名称", "规模"], ["1", "A村", "100人"]]}]
it = judge_targets_table(FakeRep(["", ""], tables=tbl_no_pos), FakeEx())
check("缺方位 → 建议", it.AI审核 != S_OK, it.AI审核)
# 政策条文表里出现"生态环境保护目标""距离"字样，不能被当成保护目标表
tbl_trap = [{"page": 5, "rows": [
    ["政策要求", "新建、扩建项目应符合生态环境保护法律法规要求"],
    ["选址", "严格落实地址要求，与敏感目标保持距离"],
    ["其他", "按有关规定办理"]]}]
it = judge_targets_table(FakeRep(["", ""], tables=tbl_trap), FakeEx())
check("政策条文表 → 不得判无问题", it.AI审核 != S_OK, it.AI审核)

# ---------------------------------------------------------------- 9. 编制要素
print("\n[9] 编制要素完整性（章节标题必须含要素词）")
pages = ["封面", "第1章 概述\n1.1 企业概况", "第3章 工程分析\n3.1 工艺流程",
         "3.2 污染源分析", "第5章 环境影响预测与评价", "第11章 环境风险评价",
         "第8章 环境保护措施", "第12章 结论"]
it = judge_completeness(FakeRep(pages), FakeEx(), "报告书")
check("七要素齐 → 无问题", it.AI审核 == S_OK, it.AI审核)
check("  章级标题定位到环境风险章", ("环境风险", 6) in it.判据轨迹["已定位要素"],
      str(it.判据轨迹["已定位要素"]))
missing = ["封面", "第1章 概述", "第3章 工程分析"]
it = judge_completeness(FakeRep(missing), FakeEx(), "报告书")
check("缺要素 → 疑似（不直接判缺项）", it.AI审核 == S_SUSPECT, it.AI审核)
check("  列出未定位要素", bool(it.需人工确认), str(it.需人工确认))

print(f"\n==== 通过 {OK} / 失败 {FAIL} ====")
if FAILS:
    print("失败项：")
    for f in FAILS:
        print("  -", f)
sys.exit(1 if FAIL else 0)