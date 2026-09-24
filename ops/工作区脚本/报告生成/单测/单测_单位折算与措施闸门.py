#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C10-③（单位折算不再丢数据）与 C9（措施闸门 / 无措施事实不写该节）的单测。

为什么要单独守这两条：
  · **单位折算**：改成白名单时，"万吨/kg 填报"会被**静默丢弃** —— 判据层只会说"缺事实"，
    用户看到的是"判不了"，而错误出在**看不到的地方**。这类必须有用例钉住。
  · **措施闸门**：这是"防编造"的最后一道。必须同时验**正例**（事实表里有 → 保留）
    与**反例**（事实表里没有 → 剔除），否则闸门一收紧就会误杀正确叙述。

跑法（本地）：
  EIA_CRITERIA_DIR=<工作区>\\判据库  python 单测_单位折算与措施闸门.py
服务器上直接 python3 跑即可（判据目录走默认 /data/fagui_rag/criteria）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 报告生成/单测/
BASE = os.path.dirname(HERE)                               # 报告生成/
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from gen.decide import material_facts                       # noqa: E402
from gen.narrate import (MEASURE_WORDS, PROMPT_VERSION, _has_measure,  # noqa: E402
                        build_facts, gate, narrate)

PASS, FAIL = [], []


def check(name, got, want):
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  [{'✓' if ok else ''}] {name}: got={got!r} want={want!r}")


def main() -> int:
    print("\n== 1. C10-③ 单位折算（主要原辅材料 → 事实，单位统一折算成吨）")
    fs = material_facts({"主要原辅材料": [
        {"名称": "环氧树脂", "年用量": 1.2, "单位": "万吨"},
        {"名称": "溶剂型胶粘剂", "年用量": 12, "单位": "吨/年"},
        {"名称": "催化剂", "年用量": 500, "单位": "kg"},
        {"名称": "冷却水循环泵", "年用量": 10, "单位": "千瓦"},     # 维度不同 → 跳过
        {"名称": "", "年用量": 5, "单位": "吨"},                    # 无名称 → 跳过
        {"名称": "天然气", "年用量": None, "单位": "万立方米"},      # 无数值 → 跳过
        {"名称": "甲醇（字符串填报）", "年用量": "3,000", "单位": "吨"},   # 页面样例就是字符串
    ]})
    got = {f.category: f.value for f in fs}
    check("万吨被折算（1.2 万吨 → 12000 吨）", got.get("环氧树脂"), 12000.0)
    check("吨/年 原样保留", got.get("溶剂型胶粘剂"), 12.0)
    check("kg 被折算（500 kg → 0.5 吨）", got.get("催化剂"), 0.5)
    check("字符串年用量也能认（\"3,000\" → 3000 吨）", got.get("甲醇（字符串填报）"), 3000.0)
    check("维度不同的单位不进事实表", "冷却水循环泵" in got, False)
    check("无名称为空的不进事实表", "" in got, False)
    check("无年用量的不进事实表", "天然气" in got, False)
    quo = [f.quote for f in fs if f.category == "环氧树脂"][0]
    check("换算过程写进 quote（看得见）", "折合" in quo and "12000" in quo, True)
    quo_t = [f.quote for f in fs if f.category == "溶剂型胶粘剂"][0]
    check("本来就是吨的不写多余换算", "折合" in quo_t, False)

    print("\n== 2. C9-② 措施名出处闸门")
    facts = [{"id": "F1", "text": "环境保护措施：活性炭吸附装置；废气经 15m 排气筒排放"},
             {"id": "F2", "text": "主要工艺流程：混料→挤出→冷却"}]
    g = gate("废气采用布袋除尘器处理后经排气筒排放。", facts)
    check("事实里没有「布袋除尘」→ 正文为空", g["保留"], "")
    check("剔除原因写明措施名无出处",
          any("措施名无出处" in d["原因"] and "布袋除尘" in d["原因"] for d in g["剔除"]), True)
    g2 = gate("废气采用活性炭吸附装置处理。", facts)
    check("事实里有「活性炭」→ 保留", bool(g2["保留"]), True)
    check("保留的句子不会被误杀", g2["剔除"], [])
    # 无数字、无措施词的普通句：仍按原规则放行（不因这次改动变严）
    g3 = gate("本项目位于工业园区内。", facts)
    check("既无数字也无措施词的句子照常放行", g3["保留"].strip(), "本项目位于工业园区内。")
    check("措施词表非空且是元组", isinstance(MEASURE_WORDS, tuple) and len(MEASURE_WORDS) > 20, True)
    check("PROMPT_VERSION 已升版（否则命中旧缓存）", PROMPT_VERSION, "narr-v2")

    print("\n== 3. C9-① 没有实质「环保措施」内容时，不生成该节（实测：字段是必填，空行才是常态）")
    data_bare = {"项目名称": "某技改项目", "主要原辅材料": [{"名称": "树脂", "年用量": 10, "单位": "吨"}]}
    check("字段缺失 → 无措施", _has_measure(data_bare), False)
    check("字段在但为空列表 → 无措施", _has_measure(dict(data_bare, 环保措施=[])), False)
    check("字段在但行内没内容 → 无措施",
          _has_measure(dict(data_bare, 环保措施=[{"要素": "废气", "措施内容": "", "排放去向": ""}])), False)
    check("有真实措施内容 → 有措施",
          _has_measure(dict(data_bare, 环保措施=[{"要素": "废气", "措施内容": "活性炭吸附",
                                                  "排放去向": "15m 排气筒"}])), True)
    # 没有实质措施时，narrate() 应当**直接跳过**该节（不调模型，结果里写跳过原因）
    r = narrate(dict(data_bare, 环保措施=[{"要素": "废气", "措施内容": "", "排放去向": ""}]),
                {}, sections=[("运营期环境影响和保护措施概述", "写措施概述")])
    sec = r["小节"]["运营期环境影响和保护措施概述"]
    check("空措施 → 该节正文为空", sec["正文"], "")
    check("空措施 → 写明跳过原因", "跳过原因" in sec, True)
    check("空措施 → 根本没调模型（模型原文为空）", sec["模型原文"], "")
    fb = build_facts(data_bare, {})
    check("无环保措施 → 事实表无「环境保护措施」",
          any("环境保护措施" in f["text"] for f in fb), False)
    data_full = dict(data_bare, 环保措施=[{"要素": "废气", "措施内容": "活性炭吸附", "排放去向": "15m 排气筒"}])
    ff = build_facts(data_full, {})
    check("有环保措施 → 事实表出现「环境保护措施」",
          any("环境保护措施" in f["text"] for f in ff), True)
    check("措施内容进了事实表（闸门才有得比）",
          any("活性炭吸附" in f["text"] for f in ff), True)

    print("\n== 4. 用**真实样例填报**跑闸门（不调模型）——正反两面都要试")
    import glob
    import json as _json
    cand = (glob.glob("/data/eia_report_gen/样例/*.json")
            + glob.glob(os.path.join(BASE, "样例", "*.json")))
    if not cand:
        print("     （未找到样例目录，跳过）")
    else:
        d = _json.load(open(cand[0], encoding="utf-8"))
        fs2 = build_facts(d, {})
        s = " ".join(f["text"] for f in fs2)
        print("     样例：%s（事实表 %d 条）" % (os.path.basename(cand[0]), len(fs2)))
        has = [w for w in MEASURE_WORDS if w in s]
        not_has = [w for w in MEASURE_WORDS if w not in s]
        print("     事实表里出现的措施词：%s" % (has[:6] or "（无）"))
        if has:
            g2 = gate("运营期废气经%s处理后排放。" % has[0], fs2)
            check("事实里有的措施名（%s）→ 保留" % has[0], bool(g2["保留"]), True)
        if not_has:
            g3 = gate("运营期废气经%s处理后排放。" % not_has[0], fs2)
            check("事实里没有的措施名（%s）→ 剔除" % not_has[0],
                  any("措施名无出处" in x["原因"] for x in g3["剔除"]), True)

    print(f"\n==== 通过 {len(PASS)} / 失败 {len(FAIL)} ====")
    for f in FAIL:
        print("  失败：", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
