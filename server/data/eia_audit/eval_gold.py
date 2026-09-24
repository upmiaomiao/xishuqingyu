#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gold 评测：用「人工修改」当标准答案，算 AI 审核项的准确率。

为什么 gold 用"人工修改前后差异"而不是另做一套标注：
  审核员在实际使用中会把 AI 结论改成对的（或确认无误）。这些改动**天然就是标注**，
  不用额外让人再标一遍，也不会出现"标注标准和实际使用两套口径"的问题。

gold 文件格式（服务端保存人工修改时写这个结构）：
  {"name": "...", "items": {"审核项": {"人工修改": "存在问题", "备注": "...", "人": "张三",
                                       "时间": "..."}}, "版本": "..."}

指标：
  · 已复核项数 / 覆盖率            —— 有多少项人工看过（没看的不算分，避免虚高）
  · 一致率（AI == 人工）           —— 逐项
  · 分歧清单（按严重度排序）        —— 便于回看是"漏报"还是"误报"
  · 漏报/误报分向：AI 说没问题但人工判有问题 = 漏报（最危险）；反之为误报
  · 「存在问题」精确率/召回率       —— 这四态里最要紧的一档

用法：
  python 评测_gold.py                    # 评 _审核结果/ 下所有有 gold 的报告
  python 评测_gold.py --gold-dir 路径
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit.model import SEVERITY, S_OK, S_PROBLEM  # noqa: E402

SEV_NAME = {3: "重（存在问题）", 2: "中（疑似/建议）", 1: "轻", 0: "无（不影响）"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find_pairs(result_dir: str, gold_dir: str):
    """配对 AI 结果与 gold。

    只扫结果目录**根下的 json**：导出物放在 `导出/` 子目录、人工复核在 `人工/` 子目录，
    不能混进来 —— 否则一份报告会被算成两份（实测踩坑）。
    """
    pairs = []
    for jf in sorted(glob.glob(os.path.join(result_dir, "*.json"))):
        base = os.path.basename(jf)[:-5]
        if base.endswith(".导出") or base.endswith(".审核表") or base.startswith("gold评测"):
            continue
        cands = [g for g in glob.glob(os.path.join(gold_dir, "*.json"))
                 if os.path.basename(g)[:-5] in base or base in os.path.basename(g)[:-5]]
        if cands:
            pairs.append((base, jf, cands[0]))
    return pairs


def eval_one(ai: dict, gold: dict) -> dict:
    gitems = gold.get("items") or {}
    rows, missing = [], 0
    for it in ai.get("items", []):
        g = gitems.get(it["审核项"])
        human = (g or {}).get("人工修改") or ""
        if not human:                    # 人工没看过的项不计分（不虚高、不虚低）
            missing += 1
            continue
        ai_v = it.get("AI审核") or ""
        rows.append({"审核项": it["审核项"], "AI": ai_v, "人工": human,
                     "一致": ai_v == human,
                     "严重度差": SEVERITY.get(ai_v, 0) - SEVERITY.get(human, 0),
                     "AI置信度": it.get("置信度"),
                     "备注": (g or {}).get("备注", "")})
    n = len(rows)
    agree = sum(1 for r in rows if r["一致"])
    # 漏报：AI 判"无问题/建议"，人工判"存在问题"或"疑似"（最危险的错）
    miss = [r for r in rows if SEVERITY.get(r["人工"], 0) >= 2 and SEVERITY.get(r["AI"], 0) <= 1]
    over = [r for r in rows if SEVERITY.get(r["AI"], 0) >= 2 and SEVERITY.get(r["人工"], 0) <= 1]
    def pr(state):
        tp = sum(1 for r in rows if r["人工"] == state and r["AI"] == state)
        fp = sum(1 for r in rows if r["AI"] == state and r["人工"] != state)
        fn = sum(1 for r in rows if r["人工"] == state and r["AI"] != state)
        p = tp / (tp + fp) if tp + fp else None
        rc = tp / (tp + fn) if tp + fn else None
        return {"精确率": None if p is None else round(p, 3),
                "召回率": None if rc is None else round(rc, 3), "TP": tp, "FP": fp, "FN": fn}
    return {"已复核": n, "未复核": missing,
            "一致": agree, "一致率": round(agree / n, 3) if n else None,
            "漏报": miss, "误报": over,
            "存在问题": pr(S_PROBLEM), "无问题": pr(S_OK),
            "明细": sorted(rows, key=lambda r: -abs(r["严重度差"]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--result-dir", default=os.path.join(HERE, "_审核结果"))
    ap.add_argument("--gold-dir", default=os.path.join(HERE, "_审核结果", "人工"))
    ap.add_argument("--out", default=os.path.join(HERE, "_审核结果", "gold评测.json"))
    a = ap.parse_args()
    pairs = find_pairs(a.result_dir, a.gold_dir)
    if not pairs:
        print(f"未找到成对的（AI 结果 + 人工修改）。")
        print(f"  AI 结果目录：{a.result_dir}")
        print(f"  gold 目录  ：{a.gold_dir}（需 <报告名>.json，含 items:{{审核项:{{人工修改:…}}}}）")
        print("\n提示：在审核页面把 AI 结论改成正确值并保存，就会生成 gold 文件；"
              "改过的项即视为人工已复核。")
        return 0
    allrows, total = [], {"已复核": 0, "一致": 0}
    for base, jf, gf in pairs:
        r = eval_one(load_json(jf), load_json(gf))
        total["已复核"] += r["已复核"]
        total["一致"] += r["一致"]
        print(f"\n== {base[:52]}")
        print(f"   已复核 {r['已复核']} 项 / 未复核 {r['未复核']} 项；"
              f"一致率 {r['一致率'] if r['一致率'] is not None else '—'}")
        for m in r["漏报"]:
            print(f"   [漏报] {m['审核项']}：AI={m['AI']} 人工={m['人工']}（{m['备注'][:40]}）")
        for m in r["误报"]:
            print(f"   [误报] {m['审核项']}：AI={m['AI']} 人工={m['人工']}（{m['备注'][:40]}）")
        allrows.append({"报告": base, **{k: v for k, v in r.items() if k != "明细"},
                        "明细": r["明细"]})
    rate = round(total["一致"] / total["已复核"], 3) if total["已复核"] else None
    print(f"\n==== 汇总：已复核 {total['已复核']} 项，一致率 {rate} ====")
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"汇总": {"已复核": total["已复核"], "一致": total["一致"], "一致率": rate},
                   "报告": allrows}, f, ensure_ascii=False, indent=1)
    print("明细已写入", a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())