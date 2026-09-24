#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A3 修法验证（只读，不调模型、不落盘）：废气污染物清单还会不会被废水表污染。

用户反馈原话：「废气污染物清单页抽到"其中动植物油参照 GB8987-1996 一级标准"，
GB8978 是《污水综合排放标准》……」—— 判定大气专项用的那份"废气清单"，
其实是从**废水表**里抽出来的，结论自然不可信。

修了两处（`audit/extract.py::pollutant_terms` + `audit/items_extra.py`）：
  ① 正则里的裸 `氨` 改 `氨(?!氮)`：废水表里的「氨氮」不再把那一页拉进废气清单；
  ② 万一还是抽到废水内容，就记"疑似串页"（强=废水标准号／弱=水质指标），
     判据层据此挂「需人工核对」并给页码。

本脚本两层验证：
  A. **单元级**（构造一小段文本，直接用线上模块自己的正则跑）：
     「氨氮」不得命中、「氨」必须命中 —— 证明改的是模块本身，不是我在这里另抄一份。
  B. **报告级**：对 6 份真实报告只跑抽取，对比新旧配方命中的页，
     并打印串页嫌疑与已存结果里的大气专项结论。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 验废气清单串页.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, "/data/eia_audit")
from audit import extract as X                      # noqa: E402
from audit.parse import load_or_parse                # noqa: E402

REPORTS = Path("/data/eia_reports")
RESULTS = Path("/data/eia_audit/_审核结果")
# 旧正则（2026-09-22 之前线上那一版，作为"改前"对照；注意其中那个**裸的 `氨`**）
OLD_PAT = (r"(非甲烷总烃|二噁英|氯化氢|氯气|氰化氢|氟化物|苯并\[a\]芘|"
           r"颗粒物|二氧化硫|氮氧化物|硫化氢|氨|汞及其化合物|镉及其化合物|"
           r"铅及其化合物|砷及其化合物|铬及其化合物|VOCs|挥发性有机物|甲苯|二甲苯|甲醛)")


class FakeRep:
    """最小可用的 rep：只实现 pollutant_terms 用到的 search()。"""

    def __init__(self, text: str):
        self.page_text = [text]

    def search(self, pattern: str, max_hits: int = 50, ctx: int = 60) -> list:
        rx = re.compile(pattern)
        out = []
        for i, t in enumerate(self.page_text, start=1):
            for m in rx.finditer(t):
                out.append({"page": i, "match": m.group(0),
                            "snippet": re.sub(r"\s+", " ",
                                              t[max(0, m.start() - ctx): m.end() + ctx]).strip()})
                if len(out) >= max_hits:
                    return out
        return out


def unit_checks() -> list:
    print("[A] 单元级：线上模块自己的正则")
    rows = [
        ("废水表里的氨氮（不应命中）", "COD 50、氨氮 4(6)、总磷 0.5，动植物油参照 GB8978 一级标准", "氨氮", False),
        ("废气里的氨（必须命中）", "废气因子：氨、硫化氢、臭气浓度", "氨", True),
        ("氨水（按子串命中，属可接受）", "脱硝用氨水储罐", "氨", True),
    ]
    bad = []
    for name, text, token, want in rows:
        got = X.pollutant_terms(FakeRep(text))
        hit = token in got["names"]
        ok = hit == want
        if not ok:
            bad.append(name)
        print("  %s %s（命中=%s，清单=%s）" % ("√" if ok else "×", name, hit, got["names"]))
    # 串页嫌疑识别本身
    got = X.pollutant_terms(FakeRep("废气：颗粒物、二氧化硫；废水：COD、氨氮，执行 GB8978 三级标准"))
    print("  %s 同一页混排时能记下强嫌疑：%s" % ("√" if got["suspect_std"] else "×",
                                        got["suspect_std"]))
    if not got["suspect_std"]:
        bad.append("强嫌疑识别")
    got2 = X.pollutant_terms(FakeRep("废气：颗粒物；废水指标 COD 与总磷"))
    print("  %s 只有水质指标时记弱嫌疑：%s" % ("√" if got2["suspect_water"] else "×",
                                      got2["suspect_water"]))
    if not got2["suspect_water"]:
        bad.append("弱嫌疑识别")
    return bad


def main() -> int:
    bad = unit_checks()
    print("\n[B] 报告级：6 份真实报告")
    pdfs = sorted(p for p in REPORTS.glob("*.pdf") if not p.name.endswith("(1).pdf"))
    summary = []
    for p in pdfs:
        res = RESULTS / (p.stem + ".json")
        old_item = {}
        if res.is_file():
            try:
                j = json.loads(res.read_text(encoding="utf-8"))
                for it in j.get("items") or []:
                    if (it.get("审核项") or "").startswith("大气"):
                        old_item = it
            except Exception as e:                              # noqa: BLE001
                print("   （读已存结果失败：%s）" % e)
        try:
            rep = load_or_parse(str(p))
        except Exception as e:                                  # noqa: BLE001
            print("【%s】打不开：%s" % (p.name[:40], e))
            continue
        new = X.pollutant_terms(rep)
        # 新配方命中的页直接取模块自己算出来的 new["pages"]（不再在脚本里抄一遍正则）
        old_pages = [h["page"] for h in rep.search(OLD_PAT, max_hits=6, ctx=60)]
        new_pages = new["pages"]
        extra = sorted(set(old_pages) - set(new_pages))
        print("=" * 92)
        print("【%s】" % p.name[:70])
        print("  新配方废气清单：%s" % ("、".join(new["names"]) or "（没抽到）"))
        print("  页 %s；旧配方多命中页（裸氨造成）：%s" % (new["pages"], extra or "无"))
        print("  串页嫌疑 强=%s 弱=%s" % (new.get("suspect_std") or "无",
                                     new.get("suspect_water") or "无"))
        if old_item:
            print("  已存结果里的大气专项：%s ｜ %s"
                  % (old_item.get("AI审核"), (old_item.get("理由") or "")[:110]))
        summary.append({"报告": p.name, "清单": new["names"], "页": new["pages"],
                        "旧配方多命中页": extra,
                        "强嫌疑": new.get("suspect_std") or [],
                        "弱嫌疑": new.get("suspect_water") or [],
                        "已存大气结论": old_item.get("AI审核")})
    out = Path("/home/test/_废气清单串页验证.json")
    out.write_text(json.dumps({"单元级问题": bad, "报告级": summary},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    n_fixed = sum(1 for s in summary if s["旧配方多命中页"])
    n_strong = sum(1 for s in summary if s["强嫌疑"])
    n_weak = sum(1 for s in summary if s["弱嫌疑"] and not s["强嫌疑"])
    print("\n" + "=" * 92)
    print("小结：单元级问题 %d 个；旧配方多命中（裸氨把废水页拉进来）的报告 %d/%d；"
          "新配方下强嫌疑 %d 份、弱嫌疑 %d 份" % (len(bad), n_fixed, len(summary), n_strong, n_weak))
    print("→ %s" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
