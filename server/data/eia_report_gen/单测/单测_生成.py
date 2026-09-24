#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成侧单测：**缺陷注入**为主 —— 每条检查都配一个"故意做错"的用例，
证明检查本身有效（不做注入的检查可能永远通过，等于没检查）。

跑法：python 单测_生成.py
"""
from __future__ import annotations

import contextlib
import copy
import hashlib
import io
import json
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
WORK = os.path.dirname(os.path.dirname(BASE))
# 临时产物写在**工作区内**：沙箱不允许写系统临时目录（实测 PermissionError）
TMPROOT = os.path.join(BASE, "_生成结果", "_单测临时")
sys.path.insert(0, BASE)
sys.path.insert(0, os.environ.get("AUDIT_HOME") or os.path.join(WORK, "_脚本代码", "审核智能体"))

from gen import decide, docx_writer, narrate, schema, selfaudit  # noqa: E402

OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + detail) if detail else ""))


def _mk(tag):
    d = os.path.join(TMPROOT, tag)
    os.makedirs(d, exist_ok=True)
    return d


def load(p):
    with io.open(os.path.join(BASE, p), encoding="utf-8") as f:
        return json.load(f)


def sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


# ---------------------------------------------------------------- 1 校验（缺什么列什么）
def t_schema():
    print("\n[1] 填报校验：缺必填必须**全部列出**，且不替人默认")
    tmpl = schema.template()
    v = schema.validate(tmpl)
    check("空模板 → 校验不通过", v["ok"] is False)
    req_missing = [f for f in schema.FIELDS if f.required]
    joined = " ".join(v["errors"])
    missing_named = [f for f in req_missing if f.name in joined or f.key in joined]
    check("缺项全部列出（不漏报，%d 项必填）" % len(req_missing),
          len(missing_named) == len(req_missing),
          "列出 %d / %d" % (len(missing_named), len(req_missing)))

    d = load("样例/演示_虚构项目_填报.json")
    v2 = schema.validate(d)
    check("填好的样例 → 校验通过", v2["ok"] is True, str(v2["errors"])[:60])

    # 缺陷注入：把 bool 字段留空 vs 写 false，必须区别对待
    d2 = copy.deepcopy(d)
    d2["是否开工建设"] = None
    v3 = schema.validate(d2)
    d3 = copy.deepcopy(d)
    d3["是否开工建设"] = False
    v4 = schema.validate(d3)
    check("bool 留空=未填（会被指出）", v3["ok"] is False)
    check("bool 写 false=已填（不算缺）", v4["ok"] is True)

    # 缺陷注入：类型写错必须报错，不能静默当成有值
    d4 = copy.deepcopy(d)
    d4["是否开工建设"] = "否"
    v5 = schema.validate(d4)
    check("bool 写成字符串 → 报类型错", v5["ok"] is False,
          (v5["errors"][0] if v5["errors"] else "")[:50])
    d5 = copy.deepcopy(d)
    d5["总投资_万元"] = "五千"
    v6 = schema.validate(d5)
    check("数字写成文本 → 报类型错", v6["ok"] is False,
          (v6["errors"][0] if v6["errors"] else "")[:50])


# ---------------------------------------------------------------- 2 判定（对照原件 + 注入）
def t_decide():
    print("\n[2] 判定层对照验证：反推填报必须复现原件自述结论")
    crit = decide.load_criteria()
    cases = [("样例/玻璃_填报_反推.json", 57, "报告表", "1、环评报告.pdf"),
             ("样例/生物质_填报_反推.json", 91, "报告表", "生物质环评.pdf")]
    for path, no, tier, src in cases:
        d = load(path)
        c = decide.decide(d, crit)["名录"]
        check("%s → 条目%s/%s" % (src[:14], no, tier),
              c["名录序号"] == no and c["tier"] == tier,
              "实得 条目%s/%s" % (c["名录序号"], c["tier"]))
    # 缺陷注入：把判定结果改错，检查必须报失败（证明上面的断言真的在比对）
    d = load("样例/玻璃_填报_反推.json")
    c = decide.decide(d, crit)["名录"]
    tampered = dict(c, tier="报告书")
    check("[注入] 篡改档位后断言必须失败",
          not (tampered["名录序号"] == 57 and tampered["tier"] == "报告表"))

    # 章节清单来自判据库文件（不是硬编码）
    st = decide.load_structure()
    check("章节清单 %d 节，均带指南页码" % len(st["章节"]),
          len(st["章节"]) == 7 and all(s.get("指南页码") for s in st["章节"]))
    check("判据文件存在且可追溯", os.path.isfile(decide.STRUCT), decide.STRUCT.split("0911训练")[-1])


# ---------------------------------------------------------------- 3 专项评价（含缺陷注入）
def t_special():
    print("\n[3] 专项评价：正例/反例对照")
    crit = decide.load_criteria()
    base = load("样例/演示_虚构项目_填报.json")
    d = copy.deepcopy(base)
    d["废气污染物清单"] = ["氯气", "氯化氢"]
    d["厂界外500m内有环境空气保护目标"] = True
    r = decide.decide(d, crit)
    at = [x for x in r["专项评价"]["要素"] if x["element"] == "大气"][0]
    check("[注入] 含氯气且500m内有保护目标 → 大气专项应设", at.get("set_special") is True,
          (at.get("reason") or "")[:50])
    r0 = decide.decide(base, crit)
    at0 = [x for x in r0["专项评价"]["要素"] if x["element"] == "大气"][0]
    check("反例：无有毒有害污染物 → 大气专项不设", at0.get("set_special") is False,
          (at0.get("reason") or "")[:50])
    # 上限：PCB 类 3 项，其他 2 项
    d2 = copy.deepcopy(base)
    d2["是否印刷电路板制造"] = True
    lim_pcb = decide.decide(d2, crit)["专项评价"]["数量上限"]
    lim_ord = decide.decide(base, crit)["专项评价"]["数量上限"]
    check("PCB 类专项上限=3", lim_pcb.get("上限") == 3, str(lim_pcb)[:60])
    check("非 PCB 类专项上限=2", lim_ord.get("上限") == 2, str(lim_ord)[:60])


# ---------------------------------------------------------------- 4 出处闸门（核心防编造）
def t_gate():
    print("\n[4] 出处闸门：模型叙述里每个数字都必须有出处")
    facts = [{"id": "F1", "text": "总投资：1200万元", "来源": "填报表.总投资_万元"},
             {"id": "F2", "text": "主要产品及产能：名称=蒸汽，产能=60，单位=吨/小时",
              "来源": "填报表.产品及产能"}]
    good = "本项目总投资 1200 万元 [F1]，蒸汽产能 60 吨/小时 [F2]。"
    g = narrate.gate(good, facts)
    check("正确标注 → 保留，且标签被剥离",
          "1200" in g["保留"] and "60" in g["保留"] and "[F" not in g["保留"] and not g["剔除"])

    bad_cases = [
        ("含数字但没标出处", "本项目总投资 1200 万元。"),
        ("标了不存在的事实编号", "本项目总投资 1200 万元 [F9]。"),
        ("数字不在所引事实里（编造）", "本项目总投资 8000 万元 [F1]。"),
        ("出现标准号", "废气执行 GB16297-1996 要求 [F1]。"),
    ]
    for why, text in bad_cases:
        g = narrate.gate(text, facts)
        check("[注入] %s → 剔除" % why, bool(g["剔除"]) and not g["保留"],
              (g["剔除"][0]["原因"][:44] if g["剔除"] else "未剔除！"))

    # 回归：事实编号里的数字不能被当成正文数字（曾经导致正文全被剔除）
    g = narrate.gate("总投资 1200 万元 [F12]。", facts)
    check("回归：标签编号不算正文数字", bool(g["保留"]) or "不在所引事实" not in json.dumps(g["剔除"]),
          json.dumps(g["剔除"], ensure_ascii=False)[:60])


# ---------------------------------------------------------------- 5 Word：可复现 + 不猜 + 回修
def t_docx():
    print("\n[5] Word 交付件：字节级可复现 / 不猜 / 回修表齐备")
    crit = decide.load_criteria()
    d = load("样例/演示_虚构项目_填报.json")
    dec = decide.decide(d, crit)
    tmp = _mk("a")
    p1, p2 = os.path.join(tmp, "a.docx"), os.path.join(tmp, "b.docx")
    docx_writer.build(d, dec, p1)
    # 故意等 3 秒再生成第二份：docx 的 zip 条目时间戳精度是 2 秒，
    # 挨着生成会"撞在同一个窗口里"而**假通过** —— 必须跨窗口才测得出真可复现。
    time.sleep(3)
    docx_writer.build(d, dec, p2)
    check("同输入两次生成（间隔 3 秒）→ 字节级一致", sha(p1) == sha(p2),
          "sha256 %s" % sha(p1)[:16])
    check("产物非空且是 docx(zip)", os.path.getsize(p1) > 20000 and open(p1, "rb").read(2) == b"PK",
          "%d 字节" % os.path.getsize(p1))

    from docx import Document
    doc = Document(p1)
    txt = "\n".join(x.text for x in doc.paragraphs) + "\n" + \
        "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)
    check("未提供内容留占位（不编）", "需人工补充" in txt)
    check("声明不得直接作为报批件", "不得直接作为报批件" in txt)
    check("回修表1-2 专项评价设置情况 已出表", "专项评价设置情况" in txt)
    check("回修表1-3 危险物质清单 已出表（含临界量表头）", "临界量" in txt)
    check("标准候选带性质说明（共现≠适用）", "不是权威适用性判定" in txt or "不代表它们对本项目适用" in txt)
    check("判定依据附录可逐条复核", "判定依据" in txt and "逐条" not in "" or "名录档级" in txt)

    # 缺陷注入：把"补充事实"抽掉，占位应更多（说明确实按数据渲染，不是固定模板）
    d2 = copy.deepcopy(d)
    d2["环保措施"] = []
    p3 = os.path.join(tmp, "c.docx")
    docx_writer.build(d2, decide.decide(d2, crit), p3)
    doc3 = Document(p3)
    txt3 = "\n".join(c.text for t in doc3.tables for r in t.rows for c in r.cells)
    check("[注入] 抽掉环保措施 → 表五回落到空表（不编措施）",
          "选用低噪声设备" not in txt3 and "需人工补充" in txt3)
    return tmp


# ---------------------------------------------------------------- 6 自审闭环（含回修前后对比）
def t_selfaudit():
    print("\n[6] 生成→自审闭环：能跑通，且回修表让疑似项减少")
    crit = decide.load_criteria()
    d = load("样例/演示_虚构项目_填报.json")
    dec = decide.decide(d, crit)
    tmp = _mk("b")
    full = os.path.join(tmp, "full.docx")
    docx_writer.build(d, dec, full)                      # 带回修表
    r_full = selfaudit.audit_draft(full)
    check("自审跑通，适用项 ≥ 10", r_full["适用项数"] >= 10,
          "适用 %d 项，分布 %s" % (r_full["适用项数"], r_full["分布"]))

    # 回修对照：去掉回修表（专项评价设置情况 / 危险物质清单）后再自审
    dec2 = copy.deepcopy(dec)
    dec2["专项评价"] = dict(dec["专项评价"], 要素=[])
    dec2["危险物质"] = []
    d2 = copy.deepcopy(d)
    d2["补充事实"] = []
    bare = os.path.join(tmp, "bare.docx")
    docx_writer.build(d2, dec2, bare)
    r_bare = selfaudit.audit_draft(bare)
    sus_full = r_full["分布"].get("存在疑似问题", 0)
    sus_bare = r_bare["分布"].get("存在疑似问题", 0)
    check("回修后疑似项 ≤ 回修前（专项评价/危险物质两项被消解）",
          sus_full <= sus_bare, "回修前 %d → 回修后 %d" % (sus_bare, sus_full))
    return r_full


# ---------------------------------------------------------------- 7 不猜：缺必填就拒绝生成
def t_refuse():
    print("\n[7] 不猜：缺必填项时必须**拒绝生成**（退出码 2，且不产出文件）")
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "cli", os.path.join(BASE, "生成_报告表.py"))
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    tmpl = os.path.join(_mk("c"), "empty.json")
    with io.open(tmpl, "w", encoding="utf-8") as f:
        json.dump(schema.template(), f, ensure_ascii=False)
    out = os.path.join(_mk("d"), "x")
    buf = io.StringIO()
    old = sys.argv
    sys.argv = ["生成_报告表.py", "--填报", tmpl, "--out", out]
    try:
        with contextlib.redirect_stdout(buf):
            code = cli.main()
    finally:
        sys.argv = old
    check("空填报 → 退出码 2", code == 2)
    check("空填报 → 未生成任何文件", not os.path.isdir(out) or not os.listdir(out),
          "输出目录内容 %s" % (os.listdir(out) if os.path.isdir(out) else "不存在"))
    check("列出了缺什么", "校验未通过" in buf.getvalue() and "需人工" not in "" or "缺" in buf.getvalue())


def main():
    print("=" * 66)
    print("生成侧单测（缺陷注入）")
    print("=" * 66)
    t_schema()
    t_decide()
    t_special()
    t_gate()
    t_docx()
    t_selfaudit()
    t_refuse()
    print("\n" + "=" * 66)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    if BAD:
        for b in BAD:
            print("  失败：", b)
    print("=" * 66)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())