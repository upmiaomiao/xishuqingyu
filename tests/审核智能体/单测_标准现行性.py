#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2「引用标准现行性」单测（第 17 项消费『标准现行性.json』）。

守什么：
  · **表里没有的标准不判**——这一项最怕"说错了"，所以覆盖说明必须写清楚；
  · 标「软-待核」的只提示"未核实"，**不许写成断言**（宁可不说）；
  · 判据库自己口径不一致的（HJ 915—2017 属"部分代替"）要按"存疑"说，不能整体称已废止；
  · 命中"已被替代"的要给出替代标准与依据硬度。

跑法（本地）：
  EIA_CRITERIA_DIR=<工作区>\\判据库  python 单测_标准现行性.py
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 单测/
BASE = os.path.dirname(HERE)                               # 审核智能体/
if BASE not in sys.path:
    sys.path.insert(0, BASE)

from audit.items_extra import (STD_RX, _norm_std, _std_table,  # noqa: E402
                               _std_validity, judge_standard_citations)
from audit.model import S_OK, S_SUGGEST                    # noqa: E402

PASS, FAIL = [], []


def check(name, got, want):
    ok = got == want
    (PASS if ok else FAIL).append(name)
    print(f"  [{'✓' if ok else ''}] {name}: got={got!r} want={want!r}")


class FakeRep:
    """只实现 judge_standard_citations/_std_validity 用到的那点接口：search()。"""

    def __init__(self, cites):
        self.cites = cites          # [(页码, 片段)]

    def search(self, rx, max_hits=0, ctx=0):
        out = []
        for pg, snip in self.cites:
            hit = rx.search(snip) if hasattr(rx, "search") else re.search(rx, snip)
            if hit:
                out.append({"page": pg, "snippet": snip})
        return out[:max_hits] if max_hits else out


def main() -> int:
    print("\n== 1. 标准号归一")
    for a, b in (("GB 3095—2012", "GB3095-2012"), ("GB 3095–2012", "GB 3095-2012"),
                 ("GB/T 18883-2002", "GBT18883—2002")):
        check(f"{a} ≡ {b}", _norm_std(a), _norm_std(b))

    print("\n== 2. 判据表装入")
    t = _std_table()
    meta = t["_meta"]
    check("表已装入", meta["装入"], True)
    check("条目数 ≥ 20", meta["条数"] >= 20, True)
    check("按归一化标准号索引（GB3095—2012）", "GB30952012" in t, True)
    print(f"     （更新于 {meta['更新于']}，覆盖 {meta['条数']} 条，"
          f"内部不一致 {len(meta['不一致'])} 条）")

    print("\n== 3. 硬依据：引用被替代的标准 → 提示核实")
    rep = FakeRep([(3, "本项目环境空气质量执行 GB 3095—2012 二级标准。")])
    rows, cov = _std_validity(rep)
    check("检出 1 条待核实", len(rows), 1)
    if rows:
        r = rows[0]
        check("给出了替代标准或废止结论", ("已被" in r["结论"]) or ("已废止" in r["结论"]), True)
        check("附了依依据硬度", r["依据硬度"] in ("硬-官方", "硬-标准自身", "软-待核"), True)
    check("覆盖说明写明「表里没有的不判」", "表里没有的标准本项不判" in cov, True)

    print("\n== 4. 软-待核：只提示未核实，不许写成断言")
    rep2 = FakeRep([(5, "执行 GB9137-88 的规定。")])
    rows2, _ = _std_validity(rep2)
    check("软-待核条目被认出", len(rows2), 1)
    if rows2:
        check("措辞是「未核实」", "未核实" in rows2[0]["结论"], True)
        check("没有断言「已被…代替」", "已被" in rows2[0]["结论"], False)

    print("\n== 5. 口径不一致（部分代替）不能说成整体废止")
    inc = (_std_table()["_meta"]["不一致"] or {})
    if inc:
        title = list(inc)[0]
        # 从表里反查该标题对应的标准号
        no = ""
        for k, v in _std_table().items():
            if k == "_meta":
                continue
            if any(str(e.get("标题") or "") == title for e in v):
                no = str(v[0].get("标准号") or "")
                break
        rep3 = FakeRep([(7, f"依据 {no} 开展监测。")])
        rows3, _ = _std_validity(rep3)
        check(f"「{title}」被判为口径不一致", bool(rows3) and rows3[0]["结论"].startswith(
            "判据库内部口径不一致"), True)
    else:
        print("     （判据表未登记不一致条目，跳过）")

    print("\n== 6. 整项输出（第 17 项）")
    it = judge_standard_citations(rep, None)
    check("有现行性问题 → S_SUGGEST", it.AI审核, S_SUGGEST)
    check("理由里写了「现行性」", "现行性" in it.理由, True)
    check("理由里带了覆盖说明", "覆盖" in it.理由, True)
    check("列进需人工确认", len(it.需人工确认) >= 1, True)
    check("判据轨迹含现行性子项", "引用标准现行性待核实" in it.判据轨迹, True)
    it2 = judge_standard_citations(FakeRep([(9, "本项目不引用该标准。")]), None)
    check("没有命中 → S_OK", it2.AI审核, S_OK)
    check("S_OK 时也说清覆盖范围", "表里没有的标准本项不判" in it2.理由, True)

    print(f"\n==== 通过 {len(PASS)} / 失败 {len(FAIL)} ====")
    for f in FAIL:
        print("  失败：", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
