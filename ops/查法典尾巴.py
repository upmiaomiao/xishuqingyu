#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补齐法典相关的最后几项核查：①放射性污染防治法 status ②循环经济促进法是否真的没被废止
③知识图谱数据在哪、有没有法典节点。只读。
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

MD_ROOT = Path(os.environ.get("MD_ROOT") or "/data/fagui_rag/okf_bundles")
# 法典第1242条**原文列出**的 10 部（照抄，不用我自己的兜底清单）
LISTED = ["中华人民共和国环境保护法", "中华人民共和国环境影响评价法", "中华人民共和国海洋环境保护法",
          "中华人民共和国大气污染防治法", "中华人民共和国水污染防治法", "中华人民共和国土壤污染防治法",
          "中华人民共和国固体废物污染环境防治法", "中华人民共和国噪声污染防治法",
          "中华人民共和国放射性污染防治法", "中华人民共和国清洁生产促进法"]
NOT_LISTED = ["中华人民共和国循环经济促进法"]


def fm_of(p: Path) -> dict:
    t = io.open(p, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---", t, re.S)
    out = {}
    if m:
        for line in m.group(1).splitlines():
            if re.match(r"^\s*-\s", line) or ":" not in line:
                continue
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    files = {p.stem: p for p in (MD_ROOT / "生态环境法律法规").rglob("*.md")}
    print("==== 1) 法典第1242条列出的 10 部（应全部为「已废止」）====")
    bad = []
    for n in LISTED:
        p = files.get(n) or next((q for k, q in files.items() if n.replace("中华人民共和国", "") in k), None)
        if not p:
            print("  · %-30s —— 语料里没有这份" % n)
            bad.append(n)
            continue
        st = fm_of(p).get("status", "（无）")
        ok = st in ("已废止", "废止")
        print("  · %-30s status=%-6s %s" % (n, st, "✅" if ok else "⚠️ 需要改"))
        if not ok:
            bad.append(n)

    print("\n==== 2) 对照：法典第1242条**没有**列出的法律（应为「现行」，不该被误改）====")
    for n in NOT_LISTED:
        p = files.get(n) or next((q for k, q in files.items() if n.replace("中华人民共和国", "") in k), None)
        if not p:
            print("  · %-30s —— 语料里没有这份" % n)
            continue
        st = fm_of(p).get("status", "（无）")
        print("  · %-30s status=%-6s %s" % (n, st, "✅ 正确（法典没废止它）" if st == "现行" else "⚠️ 检查"))

    print("\n==== 3) 知识图谱数据在哪、有没有法典 ====")
    roots = ["/data/eia_audit", "/data/fagui_rag", "/home/test/xishu_qingyu_serve", "/data/eia_report_gen"]
    found = []
    for r in roots:
        for p in Path(r).rglob("*.json"):
            if any(k in p.name.lower() for k in ("graph", "kg", "图谱", "node", "triple")):
                found.append(p)
    print("  疑似图谱文件 %d 个：" % len(found))
    for p in found[:12]:
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        print("   · %-58s %s" % (str(p)[:58], ("提到法典 %d 次" % t.count("生态环境法典")) if "生态环境法典" in t else "无法典"))

    print("\n==== 4) 汇总 ====")
    print("  第1242条列出的法律中 status 仍不对的：%s" % (bad or "无 ✅"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
