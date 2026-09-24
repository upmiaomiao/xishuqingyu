#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据层单测（机械校验 + 缺陷注入）。

为什么必须单测：判据层是审核结论的唯一来源，一旦它错了，会输出"自信但错误"的意见
（本项目在语料侧已经吃过一次这个亏）。因此每条判据都要有正例、反例与缺陷注入。

用例来源：
  1. 截图那份报告表（聚氨酯胶水 12 t/a + 乙酸乙酯作溶剂 → 名录序号53 阈值 10 t → 应编报告书）
  2. 报告表编制技术指南 表1（大气/地表水/生态/环境风险专项评价设置条件）
  3. HJ 169-2018 附录B/C + 表2（Q→P→潜势→等级）
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（单测/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包在这里）
sys.path.insert(0, BASE)
from audit.criteria import (Criteria, Fact, parse_conditions, to_unit,  # noqa: E402
                            compare, _tier_state)

PASS, FAIL = [], []


def check(name, got, want):
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  [{'✓' if ok else ''}] {name}: got={got!r} want={want!r}")


def main():
    C = Criteria()

    # ---------- 1. 阈值条件解析 ----------
    print("\n== 1. 条件解析（阈值抽取）")
    conds = parse_conditions("以再生塑料为原料生产的；有电镀工艺的；"
                            "年用溶剂型胶粘剂10吨及以上的；年用溶剂型涂料（含稀释剂）10吨及以上的")
    thr = [c for c in conds if c.kind == "threshold"]
    check("阈值条件个数", len(thr), 2)
    check("胶粘剂条件关键词", thr[0].keyword, "年用溶剂型胶粘剂")
    check("胶粘剂条件阈值", thr[0].value, 10.0)
    check("胶粘剂条件单位", thr[0].unit, "吨")
    check("胶粘剂条件比较符", thr[0].cmp, ">=")
    qual = [c for c in conds if c.kind == "qualitative"]
    check("定性条件个数", len(qual), 2)

    # ---------- 2. 单位换算与比较 ----------
    print("\n== 2. 单位换算")
    check("t/a → 吨", to_unit(12, "t/a", "吨"), 12.0)
    check("万头 → 头", to_unit(1, "万头", "头"), 1e4)
    check("不可换算返回 None", to_unit(1, "吨", "千瓦"), None)
    # ---- C10-①/E1（2026-09-23 修）："亩"曾被写成 1.0 —— 1 亩被当成 1 平方米，差 666.7 倍 ----
    check("1 亩 → 平方米（≈666.67）", round(to_unit(1, "亩", "平方米"), 2), 666.67)
    check("30 亩 → 平方米（≈20000）", round(to_unit(30, "亩", "平方米")), 20000)
    check("1 万平方米 → 亩（≈15）", round(to_unit(1, "万平方米", "亩")), 15)
    check("亩 与 平方米 同维度（可换算）", to_unit(1, "亩", "平方米") is not None, True)
    # ---- C10-③（2026-09-23）：补 kg/千克 之后才折得动，万吨本来就有 ----
    check("万吨 → 吨", to_unit(1.2, "万吨", "吨"), 12000.0)
    check("500 kg → 吨", to_unit(500, "kg", "吨"), 0.5)
    check("1000 千克 → 吨", to_unit(1000, "千克", "吨"), 1.0)
    check(">= 比较", compare(12, ">=", 10), True)
    check(">= 比较边界", compare(10, ">=", 10), True)

    # ---- C10-① 定向：名录序号 110/111/121 的「5000 平方米」阈值 × 用"亩"填报的项目 ----
    # 这三条就是"跨单位"受损面（序号 4 海水养殖两边同为亩，系数相除抵消，不受影响）。
    print("\n== 2b. 亩 × 名录面积阈值（C10-① 定向）")
    by_no = {i.get("no"): i for i in (C.catalog or [])if isinstance(i, dict)}
    for no in (110, 111, 121):
        it = by_no.get(no) or {}
        conds = (parse_conditions(it.get("category") or "")
                 + parse_conditions(it.get("report_form") or ""))
        thr = [c for c in conds
               if c.kind == "threshold" and c.unit == "平方米" and float(c.value) == 5000.0]
        check(f"名录序号{no} 含「5000 平方米」阈值", bool(thr), True)
    check("30 亩（≈20000㎡）满足 5000㎡ 阈值", compare(to_unit(30, "亩", "平方米"), ">=", 5000.0), True)
    check("若按修前的 1.0 系数会误判不满足",
          compare(30 * 1.0, ">=", 5000.0), False)
    check(">= 比较不足", compare(9.99, ">=", 10), False)

    # ---------- 3. 截图案例：环评类别降级 ----------
    print("\n== 3. 截图案例（胶粘剂 12 t/a → 应编报告书）")
    items = C.find_items("塑料制品业 塑料零件及其他塑料制品制造 聚氨酯胶水 乙酸乙酯 溶剂型")
    check("候选条目非空", len(items) > 0, True)
    item = next((x for x in items if x["no"] == 53), items[0])
    check("命中名录序号", item["no"], 53)
    facts = [Fact(name="聚氨酯胶水", value=12.0, unit="t/a", category="溶剂型胶粘剂",
                  page=19, quote="聚氨酯胶水用量12t/a，以乙酸乙酯作溶剂")]
    d = C.decide_env_category([item], facts)
    check("判定成立", d["decided"], True)
    check("应编档位", d["tier"], "报告书")
    check("依据含阈值比较", "12" in d["basis"]["hit_detail"] and "10" in d["basis"]["hit_detail"], True)
    print(f"     理由：{d['basis']['hit_detail']}")

    # ---------- 4. 缺陷注入：用量降到 8 t/a ----------
    print("\n== 4. 缺陷注入：用量 12→8 t/a（应降到报告表档）")
    neg = [Fact(name="以再生塑料为原料生产", present=False, category="以再生塑料为原料生产的",
                page=10, quote="本项目原料为外购聚丙烯颗粒，不以再生塑料为原料"),
           Fact(name="电镀工艺", present=False, category="有电镀工艺的",
                page=12, quote="本项目无电镀工艺"),
           Fact(name="溶剂型涂料", present=False, category="年用溶剂型涂料（含稀释剂）",
                page=12, quote="本项目不使用溶剂型涂料")]
    facts2 = [Fact(name="聚氨酯胶水", value=8.0, unit="t/a", category="溶剂型胶粘剂",
                   page=19, quote="聚氨酯胶水用量8t/a")] + neg
    d2 = C.decide_env_category([item], facts2)
    check("不再判报告书", d2["tier"] != "报告书", True)
    check("落到报告表兜底档", d2["tier"], "报告表")
    check("兜底档被标记", d2.get("residual"), True)
    check("除外情形无法核实 → unknown（诚实降级）", d2.get("exclusion_state"), "unknown")
    check("给出 caveat", bool(d2.get("caveat")), True)

    # ---------- 4b. 缺陷注入：落入报告表栏的「除外情形」 ----------
    print("\n== 4b. 缺陷注入：非溶剂型低VOCs涂料 8 t/a → 落入除外情形（需降级为疑似）")
    facts2b = facts2 + [Fact(name="非溶剂型低VOCs含量涂料", value=8.0, unit="t/a",
                             category="年用非溶剂型低VOCs含量涂料",
                             page=20, quote="使用非溶剂型低VOCs含量涂料8t/a")]
    d2b = C.decide_env_category([item], facts2b)
    check("除外情形被命中", d2b.get("exclusion_state"), "hit")
    check("给出 caveat", bool(d2b.get("caveat")), True)
    print(f"     caveat：{d2b.get('caveat')}")

    # ---------- 5. 缺事实：不得判违规 ----------
    print("\n== 5. 缺事实 → unknown（不得判违规）")
    d3 = C.decide_env_category([item], [])
    check("结论未定", d3["decided"], False)
    check("标记 unknown", d3["unknown"], True)
    st = _tier_state(item["_cond"]["报告书"], [])
    check("报告书档状态", st["state"], "unknown")

    # ---------- 6. 专项评价（污染影响类，截图事实） ----------
    print("\n== 6. 专项评价设置（截图事实）")
    f_screen = {
        "废气污染物清单": ["非甲烷总烃"],
        "厂界外500米内是否有环境空气保护目标": False,
        "废水是否直排": False,
        "废水分向": "生活污水经化粪池预处理后排入耿车镇污水处理厂（间接排放）",
        "是否涉及集中式饮用水水源或特殊地下水资源保护区": False,
    }
    res = {r["element"]: r for r in C.eval_special_industrial(f_screen)}
    check("大气无需设置", res["大气"]["set_special"], False)
    check("地表水无需设置", res["地表水"]["set_special"], False)
    check("地下水无需设置", res["地下水"]["set_special"], False)
    check("大气理由点名非甲烷总烃", "非甲烷总烃" in res["大气"]["reason"], True)
    check("土壤固定为否", res["土壤"]["set_special"], False)
    check("声环境固定为否", res["声环境"]["set_special"], False)

    # ---------- 7. 缺陷注入：改成含二噁英 + 500m 内有敏感目标 ----------
    print("\n== 7. 缺陷注入：废气含二噁英且500m内有保护目标 → 应设置大气专项")
    f2 = dict(f_screen, **{"废气污染物清单": ["\u4e8c\u5641\u82f1", "颗粒物"],
                           "厂界外500米内是否有环境空气保护目标": True})
    r2 = {r["element"]: r for r in C.eval_special_industrial(f2)}
    check("大气需设置", r2["大气"]["set_special"], True)

    # ---------- 8. 缺陷注入：废水改为直排 ----------
    print("\n== 8. 缺陷注入：废水改直排（非槽罐车外送）→ 应设置地表水专项")
    r3 = {r["element"]: r for r in C.eval_special_industrial(dict(f_screen, **{"废水是否直排": True}))}
    check("地表水需设置", r3["地表水"]["set_special"], True)
    r4 = {r["element"]: r for r in C.eval_special_industrial(
        dict(f_screen, **{"废水是否直排": True, "是否槽罐车外送污水处理厂": True}))}
    check("槽罐车外送 → 不需设置", r4["地表水"]["set_special"], False)

    # ---------- 9. 生态条 v2 修正（限定语新增河道取水） ----------
    print("\n== 9. 生态条 v2：必须『新增河道取水』∧『下游500m 三场一通道』")
    a = {r["element"]: r for r in C.eval_special_industrial(
        dict(f_screen, **{"取水口下游500米内是否有重要水生生物三场一通道": True}))}
    check("只有下游有三场一通道 → 不设置（v1 会误判为设置）", a["生态"]["set_special"], False)
    b = {r["element"]: r for r in C.eval_special_industrial(
        dict(f_screen, **{"是否新增河道取水": True,
                          "取水口下游500米内是否有重要水生生物三场一通道": True}))}
    check("两个条件都满足 → 设置", b["生态"]["set_special"], True)

    # ---------- 10. 环境风险：临界量（HJ 169 表B.1） ----------
    print("\n== 10. 环境风险专项（q ≥ 临界量）")
    check("表B.1 物质数", len(C.risk["substances"]), 385)
    s_cas = C.substance_threshold("", "75-37-6")
    check("按 CAS 查临界量", (s_cas["name"], s_cas["threshold_t"]), ("1,1-二氟乙烷", 5.0))
    r_ok = C.eval_risk_special([{"name": "1,1-二氟乙烷", "cas": "75-37-6", "q_t": 6, "page": 30}])
    check("q=6 ≥ 5 → 需设置", r_ok["set_special"], True)
    r_no = C.eval_risk_special([{"name": "1,1-二氟乙烷", "cas": "75-37-6", "q_t": 4, "page": 30}])
    check("q=4 < 5 → 不设置", r_no["set_special"], False)
    r_un = C.eval_risk_special([{"name": "某未知物质", "q_t": 100, "page": 30}])
    check("未知物质 → unknown（不判违规）", r_un["status"], "unknown")

    # ---------- 11. 风险潜势查表 ----------
    print("\n== 11. Q→P→潜势→评价等级（附录C / 表2 / 表1）")
    check("Q<1 → 潜势Ⅰ/简单分析",
          (C.risk_potential(0.5, "M4", "E3")["potential"], C.risk_potential(0.5, "M4", "E3")["level"]),
          ("Ⅰ", "简单分析"))
    p1 = C.risk_potential(50, "M1", "E1")
    check("Q=50,M1 → P1", p1["P"], "P1")
    check("P1+E1 → 潜势\u2163+", p1["potential"], "\u2163+")
    check("潜势Ⅳ+ → 一级", p1["level"], "一级")
    p4 = C.risk_potential(5, "M4", "E3")
    check("Q=5,M4 → P4", p4["P"], "P4")
    check("P4+E3 → 潜势Ⅰ", p4["potential"], "Ⅰ")
    p3 = C.risk_potential(5, "M4", "E2")
    check("Q=5,M4,E2 → P4/P4E2→Ⅱ/三级",
          (p3["P"], p3["potential"], p3["level"]), ("P4", "Ⅱ", "三级"))

    # ---------- 12. 生态影响类（报告表另一套规则） ----------
    print("\n== 12. 生态影响类（按涉及项目类别列举）")
    eco = {r["element"]: r for r in C.eval_special_ecological(
        "本项目为城市道路建设，不涉及隧道；新建水库一座；涉及环境敏感区")}
    check("水库 → 地表水专项", eco["地表水"]["set_special"], True)
    check("涉及环境敏感区 → 生态专项", eco["生态"]["set_special"], True)
    check("城市道路（不含维护/支路）→ 噪声专项", eco["噪声"]["set_special"], True)
    eco2 = {r["element"]: r for r in C.eval_special_ecological("本项目为城市道路支路维护工程")}
    check("城市道路支路维护 → 噪声不设置", eco2["噪声"]["set_special"], False)

    # ---------- 13. 判据输入缺失时不得下否定结论 ----------
    # 2026-09-22 用户反馈（江西省博信玻璃项目实测）：
    #   报告没给危险物质清单 → 原实现判"不符合设置条件 → 报告未设置 → 符合要求"（无问题）。
    # 这是把"没有证据"当成"判定为否"。空输入只能给 unknown（由判据层转成"需人工确认"）。
    print("\n== 13. 空输入不判『符合要求』（没清单≠没危险品）")
    r_empty = C.eval_risk_special([])
    check("危险物质清单为空 → status=unknown", r_empty["status"], "unknown")
    check("危险物质清单为空 → set_special 不是 False", r_empty["set_special"], None)
    check("空清单理由写明未抽到", "未抽到" in r_empty["reason"], True)
    # 反例：有清单且未超临界量时，仍然要给出明确否定结论（不能因为这次改动变成一律 unknown）
    r_ok = C.eval_risk_special([{"name": "1,1-二氟乙烷", "cas": "75-37-6", "q_t": 4, "page": 30}])
    check("有清单且未超临界量 → 仍判 decided", r_ok["status"], "decided")
    check("有清单且未超临界量 → set_special=False", r_ok["set_special"], False)

    # 大气：废气清单为空 / 命中名录物质但缺"500米内保护目标"
    f_none = {r["element"]: r for r in C.eval_special_industrial({})}
    check("废气清单为空 → status=unknown", f_none["大气"]["status"], "unknown")
    check("废气清单为空 → 理由说明未抽到", "未抽到" in f_none["大气"]["reason"], True)
    f_clean = {r["element"]: r for r in C.eval_special_industrial(
        {"废气污染物清单": ["颗粒物", "氮氧化物"], "厂界外500米内是否有环境空气保护目标": None})}
    check("清单非空且不含名录物质 → 仍判 decided（不给 unknown）",
          f_clean["大气"]["status"], "decided")
    check("清单非空且不含名录物质 → set_special=False",
          f_clean["大气"]["set_special"], False)

    print(f"\n==== 通过 {len(PASS)} / 失败 {len(FAIL)} ====")
    if FAIL:
        for f in FAIL:
            print("  失败：", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())