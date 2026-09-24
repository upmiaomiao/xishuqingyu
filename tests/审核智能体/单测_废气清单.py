#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""缺陷注入：验证「废气污染物清单不会把废水表当成废气来源」＋「串页嫌疑能挂到结论上」。

背景（用户反馈 A3，2026-09-22）：审核页的「废气污染物清单」里抽到了
「其中动植物油参照 GB8987-1996 一级标准」—— GB8978 是《污水综合排放标准》，
动植物油是废水污染物。清单被废水表污染，大气专项的结论自然不可信。

根因是一个**裸的 `氨`**：`finditer` 是子串匹配，废水表里的「氨氮」被它命中，
于是那一页（往往同时写着动植物油、GB8978）连同摘录一起进了"废气清单"。

本脚本用**假报告对象**直接喂 `pollutant_terms` 与判据层，不依赖任何 PDF：
  ① 废水表里的「氨氮」不得命中；「氨」必须命中（不能为了修这个把真因子也去掉）
  ② 同一页混排时能记下**强**嫌疑（出现废水标准号）；只出现水质指标时记**弱**嫌疑
  ③ 判据层（items_extra）在大气专项上：有强嫌疑 → 结论降为「存在疑似问题」并给页码，
     只有弱嫌疑 → 结论不动，但理由里要留一句提示
  ④ 反向用例：干净废气页不得被误挂嫌疑（否则这条守卫会把正常报告全打成疑似）

用法：python 单测_废气清单.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT_ROOT = os.path.dirname(HERE)                         # _脚本代码/审核智能体
sys.path.insert(0, AUDIT_ROOT)

from audit.extract import pollutant_terms                  # noqa: E402

OK, BAD = [], []


class FakeRep:
    """最小可用的假报告：search 与 ParsedReport.search 同语义（页码 + 片段）。"""

    def __init__(self, text: str, page: int = 1):
        self.text = text
        self.page = page

    def search(self, pattern, max_hits=50, ctx=60):
        out = []
        for m in re.finditer(pattern, self.text):
            a = max(0, m.start() - ctx)
            out.append({"page": self.page, "mark": None,
                        "match": m.group(0), "snippet": self.text[a:m.end() + ctx]})
            if len(out) >= max_hits:
                break
        return out


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:110]) if detail else ""))


def main() -> int:
    print("=" * 62)
    print("[1] 废水表里的「氨氮」不得被当成废气因子")
    # 注意语义（第一版断言在这里写错过，见 [1b]）：串页嫌疑**只在"贡献了废气因子的页"上判** ——
    # 一页只有废水内容时，它根本不会进清单，也就无所谓"污染清单"，不该挂嫌疑。
    # 用户遇到的正是"同一页既有废气因子、又抄了废水表"那种排版。
    g = pollutant_terms(FakeRep(
        "废气：颗粒物；废水：COD 50、氨氮 4(6)、总磷 0.5；动植物油参照 GB8978 一级标准"))
    check("「氨氮」不进废气清单", "氨" not in g["names"], g["names"])
    check("该页被记为强嫌疑（含废水标准号 GB8978）", bool(g["suspect_std"]), g["suspect_std"])

    print("[1b] 纯废水页不进清单、也不该挂嫌疑（反向用例：别把无关页也算成污染）")
    g = pollutant_terms(FakeRep("废水：COD 50、氨氮 4(6)、动植物油参照 GB8978 一级标准"))
    check("纯废水页不进清单", not g["names"], g["names"])
    check("纯废水页不挂嫌疑（它本来就没参与清单）",
          not g["suspect_std"] and not g["suspect_water"],
          (g["suspect_std"], g["suspect_water"]))

    print("[2] 真废气因子必须仍然认得（不能修过火）")
    g = pollutant_terms(FakeRep("废气污染因子：氨、硫化氢、臭气浓度、非甲烷总烃"))
    check("「氨」仍进清单", "氨" in g["names"], g["names"])
    check("「硫化氢/非甲烷总烃」仍在", {"硫化氢", "非甲烷总烃"} <= set(g["names"]), g["names"])
    check("干净页不得被挂嫌疑（反向用例）",
          not g["suspect_std"] and not g["suspect_water"],
          (g["suspect_std"], g["suspect_water"]))

    print("[3] 强弱两级嫌疑要分得开")
    g = pollutant_terms(FakeRep("废气：颗粒物、二氧化硫；废水：COD、总磷"))
    check("只有水质指标 → 弱嫌疑", bool(g["suspect_water"]) and not g["suspect_std"],
          (g["suspect_std"], g["suspect_water"]))
    g = pollutant_terms(FakeRep("废气：颗粒物；废水执行 GB18918 一级A"))
    check("出现废水标准号 → 强嫌疑", bool(g["suspect_std"]), g["suspect_std"])

    print("[4] 判据层：强嫌疑要挂「需人工核对」并给页码")
    from audit import items_extra
    import inspect
    src = inspect.getsource(items_extra.judge_special_element)
    check("判据层读了 suspect_std / suspect_water",
          "suspect_std" in src and "suspect_water" in src)
    check("强嫌疑把结论降为疑似（改的是 AI审核 那一项）",
          "S_SUSPECT" in src and "需人工核对" in src)
    check("给页码（把嫌疑页码做进证据）", "_ev(p," in src or "_ev(p, " in src)
    check("弱嫌疑只提示、不翻结论", "若该页实为废水表" in src)

    print("=" * 62)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
