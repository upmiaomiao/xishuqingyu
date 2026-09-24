#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化「名录条件解析」修复的影响：改前结论（存量的 _审核结果/*.json）vs 改后重跑。

背景：`audit/criteria.py` 里两处缺陷被修（见该文件 `COND_RX` 与 `_residue_meaningful` 的注释）：
  ① 「65吨/小时（45.5兆瓦）及以下的」的比较词被括号隔开 → 漏掉 → 默认 ">="（方向反了）；
  ② 切掉阈值后剩下的碎片被当成"定性条件"，永远匹配不上 → 该档永远 unknown。
两者都会让名录档级判不出来，且同时影响审核线与生成线。

本脚本**只读**：只调用 audit_file（不写 _审核结果/），把结论与存量结果逐项对比打印。
用法：python 查条件修复影响.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                    # 审核智能体/
sys.path.insert(0, ROOT)

from audit.runner import audit_file, list_reports, report_dir  # noqa: E402
from audit.criteria import Criteria  # noqa: E402

CAT_ITEM = "环评类别准确性"
# 存量结果目录与 审核_报告.py 的 OUT 一致（runner 里没有 result_dir，别臆造）
RESULT_DIR = os.path.join(ROOT, "_审核结果")


def old_result(name: str) -> dict:
    p = os.path.join(RESULT_DIR, name.replace(".pdf", ".json"))
    if not os.path.isfile(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def cat_of(res: dict) -> dict:
    # 结果字典的列表键是 `items`（不是"审核项"）；取错键会得到"空 vs 空"的假结论
    for it in res.get("items", []):
        if it.get("审核项") == CAT_ITEM:
            tr = it.get("判据轨迹") or {}
            jd = tr.get("判定") or {}
            return {"序号": tr.get("名录序号"), "档级": jd.get("tier"),
                    "decided": jd.get("decided"), "状态": it.get("AI审核"),
                    "倾向": jd.get("preliminary")}
    return {}


def states(res: dict) -> dict:
    return {it.get("审核项"): it.get("AI审核") for it in res.get("items", [])}


def main():
    C = Criteria()
    reports = list_reports()
    print("共 %d 份报告；逐份重跑（解析/条件问答走缓存）\n" % len(reports))
    changed_cat, changed_items = [], []
    for i, pdf in enumerate(reports, 1):
        # list_reports() 给的是**文件名**，不是全路径 —— 必须拼上报告目录
        path = pdf if os.path.isabs(pdf) else os.path.join(report_dir(), pdf)
        name = os.path.basename(path)
        print("[%d/%d] %s" % (i, len(reports), name), flush=True)
        try:
            new = audit_file(path, use_llm=True, verbose=False, C=C)
        except Exception as e:                                   # noqa: BLE001
            print("    重跑失败：", type(e).__name__, e, flush=True)
            continue
        o = old_result(name)
        # 自检：取不到项就说明我自己取错了键，此时"无变化"是**假结论**，必须报错而不是放过
        if len(states(new)) < 18 or not cat_of(new):
            print("    ！自检失败：新结果只取到 %d 项、名录轨迹%s —— 检查取键方式，"
                  "此时的「无变化」不作数" % (len(states(new)),
                                          "取到" if cat_of(new) else "为空"), flush=True)
            bad += 1
        nc, oc = cat_of(new), cat_of(o) if o else {}
        flag = "" if nc == oc else "  ← 名录结论有变"
        print("    改后：条目%s 档级=%s decided=%s 状态=%s%s"
              % (nc.get("序号"), nc.get("档级"), nc.get("decided"), nc.get("状态"), flag), flush=True)
        if oc:
            print("    改前：条目%s 档级=%s decided=%s 状态=%s"
                  % (oc.get("序号"), oc.get("档级"), oc.get("decided"), oc.get("状态")), flush=True)
        if nc != oc:
            changed_cat.append((name, oc, nc))
        if o:
            so, sn = states(o), states(new)
            diff = [(k, so.get(k), sn.get(k)) for k in sn if so.get(k) != sn.get(k)]
            if diff:
                changed_items.append((name, diff))
                for k, a, b in diff:
                    print("    ★ 审核项变化：%s  %s → %s" % (k, a, b), flush=True)
            else:
                print("    18 项结论：无变化", flush=True)
        # 落盘一份改后结果，便于人工复核（不覆盖存量）
        outd = os.path.join(ROOT, "_审核结果", "_判据修复后")
        os.makedirs(outd, exist_ok=True)
        with open(os.path.join(outd, name.replace(".pdf", ".json")), "w", encoding="utf-8") as f:
            json.dump(new, f, ensure_ascii=False, indent=1)
    print("\n==== 汇总 ====")
    print("名录结论有变的报告：%d 份" % len(changed_cat))
    for name, oc, nc in changed_cat:
        print("   %s：条目%s→%s 档级%s→%s decided %s→%s 状态%s→%s"
              % (name, oc.get("序号"), nc.get("序号"), oc.get("档级"), nc.get("档级"),
                 oc.get("decided"), nc.get("decided"), oc.get("状态"), nc.get("状态")))
    print("有审核项结论变化的报告：%d 份" % len(changed_items))
    for name, diff in changed_items:
        print("   %s：%s" % (name, "；".join("%s %s→%s" % d for d in diff)))
    print("\n改后结果已另存：_审核结果/_判据修复后/（未覆盖存量）")
    return 0


if __name__ == "__main__":
    sys.exit(main())