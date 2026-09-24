#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查《生态环境法典》同时废止的那几部法律，在语料里的 status 是否已经改过来。

背景：法典（2026-08-15 施行）第1242条同时废止一批法律。B1/B2 只把固废法、环评法
两部标成了"已废止"，其余几部可能还写着"现行" —— 用户说"法典是最新的"，要的应该就是这个。
本脚本只读：列出法典 supersedes 清单 + 每部法律现在的 status / status_note。
"""
from __future__ import annotations

import io
import os
import re
from pathlib import Path

MD_ROOT = Path(os.environ.get("MD_ROOT") or "/data/fagui_rag/okf_bundles")
LAW_DIR = MD_ROOT / "生态环境法律法规" / "法律"


def front_matter(p: Path) -> dict:
    t = io.open(p, encoding="utf-8", errors="ignore").read()
    m = re.match(r"^---\n(.*?)\n---", t, re.S)
    if not m:
        return {}
    fm = {}
    for line in m.group(1).splitlines():
        if re.match(r"^\s*-\s", line) or ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip()
    return fm


def main() -> int:
    code = MD_ROOT / "生态环境法律法规/法律/法律_43/中华人民共和国生态环境法典/中华人民共和国生态环境法典.md"
    if not code.is_file():
        print("没找到法典文件：%s" % code)
        return 1
    t = io.open(code, encoding="utf-8", errors="ignore").read()
    print("==== 1) 法典 front matter 里的 supersedes 清单 ====")
    m = re.match(r"^---\n(.*?)\n---", t, re.S)
    fm_raw = m.group(1) if m else ""
    in_sup = False
    superseded = []
    for line in fm_raw.splitlines():
        if re.match(r"^supersedes:", line):
            in_sup = True
            continue
        if in_sup:
            if re.match(r"^\S", line) and not line.startswith(" "):
                in_sup = False
                continue
            mm = re.match(r'^\s*-?\s*name:\s*(.+)$', line)
            if mm:
                superseded.append(mm.group(1).strip().strip('"'))
    print("  共 %d 部：%s" % (len(superseded), "、".join(superseded) or "（没解析到）"))

    print("\n==== 2) 第1242条原文（看它到底废止了哪些）====")
    i = t.find("第一千二百四十二条")
    print("  %s" % t[i:i + 700].replace("\n", " ")[:700])

    print("\n==== 3) 这些法律在语料里的 status ====")
    files = {}
    for p in LAW_DIR.rglob("*.md"):
        files[p.stem] = p
    names = superseded or ["中华人民共和国环境保护法", "中华人民共和国环境影响评价法",
                           "中华人民共和国海洋环境保护法", "中华人民共和国水污染防治法",
                           "中华人民共和国大气污染防治法", "中华人民共和国土壤污染防治法",
                           "中华人民共和国固体废物污染环境防治法", "中华人民共和国噪声污染防治法",
                           "中华人民共和国清洁生产促进法", "中华人民共和国循环经济促进法"]
    need_fix = []
    for n in names:
        p = files.get(n)
        if not p:
            # 名字可能带后缀差异，做一次包含匹配
            cand = [q for k, q in files.items() if n.replace("中华人民共和国", "") in k]
            p = cand[0] if cand else None
        if not p:
            print("  · %-30s —— 语料里没找到这份" % n)
            continue
        fm = front_matter(p)
        st = fm.get("status", "（无）")
        flag = "✅ 已改" if st in ("已废止", "废止") else "⚠️ 仍是现行"
        print("  · %-30s status=%-6s %s" % (n, st, flag))
        if st not in ("已废止", "废止"):
            need_fix.append((n, str(p)))

    print("\n==== 4) 结论 ====")
    print("  需要把 status 改成「已废止」的：%d 部" % len(need_fix))
    for n, p in need_fix:
        print("   · %s" % n)
        print("     %s" % p)
    print("\n  注：status 不在嵌入文本里，所以改它是**不需要重算向量**的（只改 front matter 与块元数据）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
