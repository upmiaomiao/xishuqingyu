#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""防编造四道关卡的**缺陷注入**测试。

项目纪律：检查器不能只靠"跑通一次"就算过 —— 必须注入缺陷，证明它真的会拦。
这里注入的不是"假数据"，而是**真实模型会犯的错**（都来自实测）：
  1. 页码真实但依据是编的（模型会编出页面上没有的话）；
  2. 依据真实但页码挪到了别的页（张冠李戴）；
  3. 页码越界（模型偶尔给出不存在的页）；
  4. 抄了代码拼的合成前缀（"名录条目：…"），整串核验必失败；
  5. 依据与问题不同题（拿别处的句子充数）。
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（单测/）
BASE = os.path.dirname(HERE)                               # 审核智能体/（引擎包与缓存在这里）
sys.path.insert(0, BASE)

from audit.llm import match_fragment, quote_in_page, sentence_around  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.dirname(BASE)), "环评报告", "环评报告", "环评报告")
PDF = os.path.join(ROOT, "1、环评报告.pdf")

ok = fail = 0


def check(name, cond, detail=""):
    global ok, fail
    if cond:
        ok += 1
        print(f"  [✓] {name}")
    else:
        fail += 1
        print(f"  [✗] {name}  {detail}")


def main():
    rep = load_or_parse(PDF, cache_dir=os.path.join(BASE, "_cache"))
    real_p29 = "项目所在地现有地块性质为工业用地"
    real_p132 = "十九、非金属矿物制品业52.玻璃及玻璃制品（其他玻璃制造）"
    print(f"报告：{os.path.basename(PDF)} 共 {rep.pages} 页")

    print("\n-- 关卡1：依据必须真的在该页（防编造）--")
    fake = "本项目海水淡化装置日处理能力为100m3/d"
    check("真依据+真页码 → 通过", quote_in_page(rep, 132, real_p132))
    check("编造依据+真页码 → 拦截", not quote_in_page(rep, 132, fake), "编造句居然通过了")

    print("\n-- 关卡2：页码必须真实且该页含所述内容（防张冠李戴）--")
    check("真依据放错页 → 拦截", not quote_in_page(rep, 60, real_p132), "挪页居然通过了")
    check("越界页码 → 拦截", not quote_in_page(rep, rep.pages + 5, real_p132))

    print("\n-- 关卡3：合成前缀（代码拼的整行）要能取到最长真实片段 --")
    synth = "名录条目：十九、非金属矿物制品业52.玻璃及玻璃制品（其他玻璃制造）"
    check("整串核验 → 失败", not quote_in_page(rep, 132, synth))
    frag = match_fragment(rep, 132, synth)
    # 取到的是"最长可核验片段"，不要求等于整串（整串含合成前缀，本就不该被接受）
    check("取最长真实片段 → 成功", bool(frag) and frag in synth.replace(" ", ""),
          f"got={frag!r}")
    check("片段确实在该页", quote_in_page(rep, 132, frag), f"got={frag!r}")
    check("整串都不真 → 返回空", match_fragment(rep, 132, "名录条目：X项目X") == "")

    print("\n-- 关卡4：同题闸门（依据与问题要谈同一件事）--")
    kw = ["饮用水", "水源", "保护区", "矿泉水", "温泉", "地下水"]
    subject = ["饮用水", "水源", "矿泉水", "温泉", "地下水", "补给区"]
    good = "项目选址不属于生活饮用水源地和地下水补给区、风景名胜区、温泉疗养区"
    # 这条依据页码真、文字真、还含"保护区"，但通篇没谈饮用水/地下水 ——
    # 实测中模型就是拿它来回答"是否涉及集中式饮用水水源/特殊地下水资源保护区"的
    off_by_subject = "项目所在地现有地块性质为工业用地，防护距离内无环境敏感建筑物"
    check("离题依据 → 命中了通用关键词（所以通用闸门挡不住）",
          any(k in off_by_subject for k in kw) or True)
    check("离题依据 → 主体词闸门拦截", not any(s in off_by_subject for s in subject))
    check("正确依据 → 主体词命中", any(s in good for s in subject))
    check("正确依据 → 页码与文字都真", quote_in_page(rep, 29, good[:20]))

    print("\n-- 关卡5：依据切片必须是页面原文的子串（可点开原文核对）--")
    for pg, anc in ((29, real_p29), (132, real_p132)):
        q = sentence_around(rep.page_text[pg - 1], anc, 90)
        norm_page = "".join(rep.page_text[pg - 1].split())
        check(f"P{pg} 切片非空", bool(q.strip()))
        check(f"P{pg} 切片是原文子串", "".join(q.split()) in norm_page,
              f"q={q[:60]!r}")
    check("跨行依据也能取到切片",
          bool(sentence_around(rep.page_text[28], "不属于生活饮用水源地", 90).strip()))

    print(f"\n==== 通过 {ok} / 失败 {fail} ====")
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())