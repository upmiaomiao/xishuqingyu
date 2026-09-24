#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离线自测判分逻辑：双向验，不花模型调用。

为什么要这个：`复测5个错例_B1B5.py` 的判断标准本身错过两次 ——
  ① 第一版 `must_all=["废止"]` 被"**未见废止**或失效声明"喂饱 → 假通过；
  ② 第二版 `ban=["仍有效"]` 把"因此**不能回答**『仍有效』"判成违规 → 假失败。
断言红了要先怀疑断言。这个脚本用两组文本对撞：
  · **用户原始错答**（反馈原件里的"模型原话"）→ 必须判违规；
  · **上一轮真跑出来的答案**（`_工作记录/复测5个错例_*.json`）→ 按人工读过的结论对答案。

用法：python 自测断言_B1B5.py
"""
from __future__ import annotations

import glob
import importlib.util
import io
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
MOD = WS / "_脚本代码" / "站点全量测试" / "复测5个错例_B1B5.py"

# 用户反馈原件里的「模型原话」（必须判违规）。取自 `_中间产物/用户反馈/反馈全文.txt`。
ORIGINAL_WRONG = {
    "B1": "根据现有证据，《固体废物污染环境防治法》2020年4月29日修订版自2020年9月1日起施行，目前仍为有效法律。",
    "B2": "最近一次修订为2018年12月29日第二次修正，该版本目前仍为有效法律，在环境影响评价活动中继续适用。",
    "B3": "GB3095-2012中PM10年平均二级浓度限值为50微克/立方米。",
    "B4": "所涉城镇污水处理厂氨氮执行地方标准DB33/2169-2018而非GB18918-2002一级A……DB33/2169-2018的具体氨氮限值未在材料中提供。",
    "B5": "总汞0.05mg/L是第一类污染物最高允许排放浓度值，表格将其列在“三级标准”列下……需查阅GB8978-1996原文确认第一类污染物的适用条件。",
}
# 人工读过、逐条确认过的结论（True=这份答案该判违规）
JUDGED = {
    "复测5个错例_改后状态标记.json": {"B1": True, "B2": True, "B3": False, "B4": False, "B5": True},
    "复测5个错例_带元数据.json": {"B1": False, "B2": True, "B3": False, "B4": False, "B5": False},
    # 带依据那轮：B2 被依据救回来（False）；B5 没有错误断言了，但**仍没答对**
    # （缺 GB8978 表1 原文，答"无法确认"）→ 按"有没有答对"仍记 True。
    "复测5个错例_带依据.json": {"B1": False, "B2": False, "B3": False, "B4": False, "B5": True},
    # 终态那轮（清掉死代码常量后）：应与"带依据"逐项一致 —— 这正是那次改动的目的。
    "复测5个错例_终态.json": {"B1": False, "B2": False, "B3": False, "B4": False, "B5": True},
}


def load_mod():
    spec = importlib.util.spec_from_file_location("t", str(MOD))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def judge(m, cid, text):
    c = [x for x in m.CASES if x["id"] == cid][0]
    must_missing = [w for w in c["must_all"] if w not in text]
    bans = [v for v in (m.violation(text, rx, ex) for rx, ex in c.get("ban_rx", [])) if v]
    return bool(must_missing or bans), must_missing, bans


def main() -> int:
    m = load_mod()
    bad = 0

    print("=" * 92)
    print("A) 用户原始错答 —— 必须判违规（判不出来=判分太松，会放过真错）")
    for cid, text in ORIGINAL_WRONG.items():
        got, miss, bans = judge(m, cid, text)
        flag = "✅" if got else "❌"
        bad += 0 if got else 1
        print(f"  {flag} {cid} 判违规={got}　缺必含词={miss or '无'}　"
              f"违规断言={(bans[0][:70] if bans else '无')}")

    print("=" * 92)
    print("B) 线上真跑出来的答案 —— 与人工判读对答案（判错=判分太严或太松，会误报）")
    for f in sorted(glob.glob(str(WS / "_工作记录" / "复测5个错例_*.json"))):
        name = Path(f).name
        want = JUDGED.get(name)
        if not want:
            print(f"  · 跳过 {name}（没有人工判读记录）")
            continue
        rows = json.load(io.open(f, encoding="utf-8"))["rows"]
        for r in rows:
            got, miss, bans = judge(m, r["id"], r["answer"])
            exp = want[r["id"]]
            flag = "✅" if got == exp else "❌"
            bad += 0 if got == exp else 1
            print(f"  {flag} {name:28s} {r['id']} 判违规={got} 人工判={exp}"
                  f"　缺必含词={miss or '无'}　违规断言={(bans[0][:60] if bans else '无')}")

    print("=" * 92)
    print(f"结论：{'全部一致 ✅' if bad == 0 else f'{bad} 处不一致 ❌（判分逻辑还需修）'}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
