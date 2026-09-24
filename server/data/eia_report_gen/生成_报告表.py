#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告生成智能体（《报告表》·污染影响类）—— 命令行入口。

用法：
    python 生成_报告表.py --模板                          # 导出填报模板
    python 生成_报告表.py --填报 样例/xxx.json             # 校验→判定→生成 docx→自审
    python 生成_报告表.py --填报 x.json --no-audit        # 跳过自审
    python 生成_报告表.py --填报 x.json --out 目录

流程（四步，缺一不可）：
    ① 校验填报：缺必填项就**停下**并列出全部缺项（不猜、不默认）
    ② 判定：名录档级 / 专项评价设置 / 章节字段清单（纯代码，可追溯）
    ③ 生成 Word：确定性内容由代码渲染，未提供的留【需人工补充】
    ④ 自审：把生成的稿子回灌审核引擎 18 项，输出问题清单（生成→自审闭环）
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from gen import decide, docx_writer, schema  # noqa: E402

OUT_DIR = os.path.join(HERE, "_生成结果")


def main():
    ap = argparse.ArgumentParser(description="环评报告表生成智能体")
    ap.add_argument("--填报", dest="form", help="项目信息填报表（json）")
    ap.add_argument("--模板", action="store_true", help="导出填报模板后退出")
    ap.add_argument("--out", default=OUT_DIR, help="输出目录（默认 _生成结果）")
    ap.add_argument("--no-audit", action="store_true", help="跳过生成后的自审")
    ap.add_argument("--模型", action="store_true",
                    help="启用模型叙述（受出处闸门约束：含数字的句子必须在事实表中有出处）")
    args = ap.parse_args()

    if args.模板 or not args.form:
        return schema.main()

    data = schema.load(args.form)
    print("=" * 68)
    print("① 校验填报：", args.form)
    v = schema.validate(data)
    print("   已填 %d / %d 字段" % (v["已填字段数"], v["字段总数"]))
    if not v["ok"]:
        print("   ✗ 校验未通过，**不生成**（缺什么就列什么，工具不替人默认）：")
        for e in v["errors"]:
            print("     -", e)
        if v["warnings"]:
            print("   提示（选填未填，将留【需人工补充】）：")
            for w in v["warnings"][:10]:
                print("     -", w)
        return 2
    print("   ✓ 校验通过")
    if v["warnings"]:
        print("   选填未填 %d 项，将留【需人工补充】：%s"
              % (len(v["warnings"]), "、".join(v["warnings"][:8])))

    print("=" * 68)
    print("② 判定（纯代码，依据可查）")
    dec = decide.decide(data)
    c = dec["名录"]
    print("   名录档级：%s%s" % (c.get("tier") or "未定", "" if c.get("decided") else
                              "（倾向 %s，事实不足）" % (c.get("倾向档位") or "?")))
    print("   命中条目：序号%s %s" % (c.get("名录序号"), c.get("名录条目")))
    if c.get("待补事实"):
        print("   为定档需补的事实（照条件原文填「补充事实」）：")
        for x in dict.fromkeys(c["待补事实"]):
            print("     -", x)
    for r in dec["专项评价"]["要素"]:
        if r.get("set_special") is True or r.get("status") == "unknown":
            print("   专项评价：%-6s %s —— %s"
                  % (r["element"], {True: "应设", False: "不设", None: "未定"}[r.get("set_special")],
                     r["reason"][:60]))
    print("   章节清单：%d 节（来源：判据库/报告表结构.json）" % len(dec["章节"]))
    if dec["需人工确认"]:
        print("   需人工确认 %d 项" % len(dec["需人工确认"]))

    narration = None
    if args.模型:
        from gen import narrate
        print("   叙述（模型，受出处闸门约束）…")
        narration = narrate.narrate(data, dec)
        n = len(narration["事实表"])
        drop = sum(len(v["剔除"]) for v in narration["小节"].values())
        print("   事实表 %d 条；模型叙述 %d 小节；**被出处闸门剔除 %d 句**"
              % (n, len(narration["小节"]), drop))
        for v in narration["小节"].values():
            for d in v["剔除"]:
                print("     ✗ %s → %s" % (d["句"][:48], d["原因"][:60]))
    print("=" * 68)
    print("③ 生成 Word")
    name = (data.get("项目名称") or "未命名项目").replace("/", "_").replace("\\", "_")
    out = os.path.join(args.out, name + "-报告表草稿.docx")
    docx_writer.build(data, dec, out, narration=narration)
    size = os.path.getsize(out)
    print("   已生成：%s（%d 字节）" % (out, size))

    if args.no_audit:
        return 0
    print("=" * 68)
    print("④ 自审（生成→自审闭环：把生成的稿子回灌审核引擎）")
    try:
        from gen import selfaudit
        res = selfaudit.audit_draft(out)
    except Exception as e:                                      # noqa: BLE001
        print("   自审不可用：%s: %s" % (type(e).__name__, e))
        return 0
    print("   适用 %d 项，结论分布：%s" % (res["适用项数"], res["分布"]))
    for it in res["需注意"]:
        print("   - [%s] %s：%s" % (it["状态"], it["审核项"], (it.get("理由") or "")[:80]))
    print("   说明：%s" % res["说明"])
    return 0


if __name__ == "__main__":
    sys.exit(main())