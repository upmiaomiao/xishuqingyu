#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[026] 第二步：确定"补哪些节点与边"的范围，并反推 id 里那 8 位哈希的算法。

只读。要回答：
  ① 图谱里有哪些 label（Law/Document/Standard/Organization/Article…）与关系词（rel）；
  ② 法典第1242条那 10 部法律，**哪些已有节点**（已有的只需加边，缺的才要加节点）；
  ③ 法典自己是 Document 还是 Law（关系到"法典 -SUPERSEDES-> 某法"这条边该怎么写）；
  ④ id 尾部 8 位十六进制是怎么算的（拿已知节点反推，试几种常见算法）。
"""
from __future__ import annotations

import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path

KG = Path("/home/test/xishu_qingyu_serve/kg_data/graph_full.json")
LISTED = ["中华人民共和国环境保护法", "中华人民共和国环境影响评价法", "中华人民共和国海洋环境保护法",
          "中华人民共和国大气污染防治法", "中华人民共和国水污染防治法", "中华人民共和国土壤污染防治法",
          "中华人民共和国固体废物污染环境防治法", "中华人民共和国噪声污染防治法",
          "中华人民共和国放射性污染防治法", "中华人民共和国清洁生产促进法"]
CODE = "中华人民共和国生态环境法典"


def node_name(nid: str, node: dict) -> str:
    p = node.get("props") or {}
    return p.get("full_name") or p.get("name") or p.get("name_zh") or p.get("article_no") or ""


def main() -> int:
    g = json.loads(io.open(KG, encoding="utf-8").read())
    nodes = g["nodes"]
    edges = g["edges"]

    print("==== 1) label 与 rel 词表 ====")
    lab = Counter(n.get("label") for n in nodes.values())
    print("  节点 label：%s" % lab.most_common())
    rel = Counter(e.get("rel") for e in edges)
    print("  关系 rel：%s" % rel.most_common())

    print("\n==== 2) 法典第1242条 10 部法律的节点情况 ====")
    have, miss = [], []
    for law in LISTED:
        hit = [(nid, n) for nid, n in nodes.items() if law in nid or law == node_name(nid, n)]
        if hit:
            have.append(law)
            for nid, n in hit[:2]:
                print("  ✅ %-30s %s  label=%s  status=%s"
                      % (law, nid, n.get("label"), (n.get("props") or {}).get("validity_status")))
        else:
            miss.append(law)
    print("  已有节点 %d 部；缺节点 %d 部：%s" % (len(have), len(miss), "、".join(miss)))

    print("\n==== 3) 法典自己的节点 ====")
    for nid, n in nodes.items():
        if CODE in nid or CODE in node_name(nid, n):
            print("  · %-58s label=%s" % (nid, n.get("label")))
            print("    props=%s" % json.dumps(n.get("props"), ensure_ascii=False)[:220])
    code_law = [nid for nid, n in nodes.items() if CODE in nid and n.get("label") == "Law"]
    print("  法典的 Law 节点：%s" % (code_law or "没有（只有 Document/Article）"))

    print("\n==== 4) 反推 id 尾部 8 位哈希 ====")
    samples = [("Law", "生态环境保护专项督察办法", "2635c28d"),
               ("Law", "中央生态环境保护督察整改工作办法", "b6042a0e")]
    # 从图里再取几个真实样本
    n_law = 0
    for nid, n in nodes.items():
        m = re.match(r"^(\w+)_(.*)_([0-9a-f]{8})$", nid)
        if m and n.get("label") == "Law" and n_law < 3:
            samples.append((m.group(1), m.group(2), m.group(3)))
            n_law += 1
    cands = {
        "md5(label|name)[:8]": lambda l, nm: hashlib.md5(("%s|%s" % (l, nm)).encode()).hexdigest()[:8],
        "md5(label_name)[:8]": lambda l, nm: hashlib.md5(("%s_%s" % (l, nm)).encode()).hexdigest()[:8],
        "md5(name)[:8]": lambda l, nm: hashlib.md5(nm.encode()).hexdigest()[:8],
        "sha1(label|name)[:8]": lambda l, nm: hashlib.sha1(("%s|%s" % (l, nm)).encode()).hexdigest()[:8],
        "md5(name+label)[:8]": lambda l, nm: hashlib.md5((nm + l).encode()).hexdigest()[:8],
    }
    for l, nm, want in samples:
        got = {k: f(l, nm) for k, f in cands.items()}
        hit = [k for k, v in got.items() if v == want]
        print("  %-28s 期望 %s → %s" % (nm[:24], want, ("命中算法：" + ",".join(hit)) if hit else got))
    print("\n  说明：若都不命中，说明哈希是构建脚本自定义（可能是 python hash 或 uuid），"
          "那补节点时就**自造一个不冲突的 8 位 hex** 即可（id 只作主键，站点按名称检索）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
