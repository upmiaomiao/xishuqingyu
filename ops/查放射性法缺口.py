#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核实《放射性污染防治法》是否真的不在语料里，并列出法律目录全貌（找其他缺口）。只读。"""
from __future__ import annotations

import io
import json
import os
from pathlib import Path

MD_ROOT = Path(os.environ.get("MD_ROOT") or "/data/fagui_rag/okf_bundles")
LAW = MD_ROOT / "生态环境法律法规" / "法律"
KG = Path("/home/test/xishu_qingyu_serve/kg_data/graph_full.json")


def main() -> int:
    print("==== 1) 法律目录全貌（每份：字数 / status）====")
    n = 0
    for d in sorted(LAW.iterdir()):
        if not d.is_dir():
            continue
        for sub in sorted(d.iterdir()):
            if sub.is_dir():
                mds = list(sub.glob("*.md"))
                for m in mds:
                    t = io.open(m, encoding="utf-8", errors="ignore").read()
                    st = ""
                    for line in t[:600].splitlines():
                        if line.startswith("status:"):
                            st = line.split(":", 1)[1].strip()
                            break
                    n += 1
                    print("  %-28s %-46s %7d 字  status=%s"
                          % (d.name, sub.name[:46], len(t), st or "（无）"))
            elif sub.suffix == ".md":
                n += 1
                print("  %-28s %-46s %7d 字" % (d.name, sub.name[:46], sub.stat().st_size))
    print("  共 %d 份法律文件" % n)

    print("\n==== 2) 全语料里搜「放射性污染防治法」（文件名或正文）====")
    hit_name, hit_text = [], []
    for p in MD_ROOT.rglob("*.md"):
        if "放射性污染防治法" in p.name or "放射性污染防治法" in str(p.parent):
            hit_name.append(p)
    print("  文件名/目录命中：%d 份" % len(hit_name))
    for p in hit_name[:10]:
        print("   · %s" % p.relative_to(MD_ROOT))
    # 正文命中抽样（只数不改）
    for p in MD_ROOT.rglob("*.md"):
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "放射性污染防治法" in t:
            hit_text.append((p.relative_to(MD_ROOT), t.count("放射性污染防治法")))
    print("  正文提到它的文件：%d 份" % len(hit_text))
    for name, c in hit_text[:10]:
        print("   · %s（%d 次）" % (name, c))

    print("\n==== 3) 图谱里有没有《放射性污染防治法》与法典的关系 ====")
    if KG.is_file():
        t = io.open(KG, encoding="utf-8", errors="ignore").read()
        print("  图谱 %d 字节；提到「放射性污染防治法」%d 次；提到「生态环境法典」%d 次"
              % (len(t), t.count("放射性污染防治法"), t.count("生态环境法典")))
        try:
            g = json.loads(t)
            print("  顶层键：%s" % list(g)[:8])
            nodes = g.get("nodes") or g.get("实体") or []
            print("  节点数：%d" % len(nodes))
            for nd in nodes:
                s = json.dumps(nd, ensure_ascii=False)
                if "生态环境法典" in s:
                    print("   · 法典节点：%s" % s[:200])
                    break
        except Exception as exc:                                    # noqa: BLE001
            print("  解析失败：%s" % exc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
