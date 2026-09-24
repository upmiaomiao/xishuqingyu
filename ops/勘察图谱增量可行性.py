#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[026] 可行性勘察：知识图谱能不能**增量**补《生态环境法典》的法律实体节点与"废止"边。

只读，不写任何文件。要点：
  ① 图谱数据文件在哪、多大、节点/边什么结构（字段名、id 命名规则）；
  ② 站点**怎么加载**它 —— 启动时整体读入（那就能改 JSON + 重启）还是每次现建（那就要跑构建链路）；
  ③ 构建脚本在不在、跑一次要多久（找 kg 相关脚本与依赖）；
  ④ 法典现在在图谱里长什么样（条级节点？有没有法律实体节点？边的类型有哪些）；
  ⑤ 若要加：加什么节点、加什么边、会不会影响现有关键词推荐/接口。
"""
from __future__ import annotations

import io
import json
import os
import re
import subprocess
from pathlib import Path

SITE = Path("/home/test/xishu_qingyu_serve")
KG = SITE / "kg_data"


def main() -> int:
    print("==== 1) 图谱数据文件 ====")
    if KG.is_dir():
        for p in sorted(KG.rglob("*")):
            if p.is_file():
                print("  · %-46s %10d 字节  %s" % (p.relative_to(KG), p.stat().st_size,
                                                   __import__("time").strftime(
                                                       "%Y-%m-%d %H:%M", __import__("time").localtime(p.stat().st_mtime))))
    else:
        print("  没有 %s" % KG)

    f = KG / "graph_full.json"
    if not f.is_file():
        print("  找不到 graph_full.json")
        return 1
    g = json.loads(io.open(f, encoding="utf-8").read())
    raw_nodes, edges = g.get("nodes") or {}, g.get("edges") or []
    # graph_full.json 的 nodes 是 **dict（id → 节点）**，不是 list —— 两种都兼容
    nodes = list(raw_nodes.values()) if isinstance(raw_nodes, dict) else list(raw_nodes)
    if isinstance(edges, dict):
        edges = list(edges.values())
    print("\n==== 2) 结构 ====")
    print("  顶层键：%s" % list(g))
    print("  nodes 容器：%s；节点 %d 个，边 %d 条"
          % (type(raw_nodes).__name__, len(nodes), len(edges)))
    print("  节点字段：%s" % (sorted(nodes[0]) if nodes else "（无节点）"))
    print("  边字段：%s" % (sorted(edges[0]) if edges else "（无边）"))
    print("  节点样例：%s" % json.dumps(nodes[:2], ensure_ascii=False)[:400])
    print("  边样例：%s" % json.dumps(edges[:2], ensure_ascii=False)[:400])
    if isinstance(raw_nodes, dict):
        print("  节点 id 样例：%s" % list(raw_nodes)[:4])

    # 节点类型分布 / 边类型分布
    def dist(objs, key):
        d = {}
        for o in objs:
            d[str(o.get(key))] = d.get(str(o.get(key)), 0) + 1
        return sorted(d.items(), key=lambda kv: -kv[1])[:12]

    print("\n  节点 type 分布：%s" % dist(nodes, "type"))
    print("  边 relation/type 分布：%s" % (dist(edges, "relation") or dist(edges, "type")))

    print("\n==== 3) 法典在图谱里的样子 ====")
    code_nodes = [n for n in nodes if "生态环境法典" in json.dumps(n, ensure_ascii=False)]
    print("  含「生态环境法典」的节点 %d 个：" % len(code_nodes))
    for n in code_nodes[:8]:
        print("   · %s" % json.dumps(n, ensure_ascii=False)[:220])
    rad = [n for n in nodes if "放射性污染防治法" in json.dumps(n, ensure_ascii=False)]
    print("  含「放射性污染防治法」的节点 %d 个" % len(rad))
    law_nodes = [n for n in nodes if n.get("type") in ("Law", "法律", "Regulation", "法规")]
    print("  疑似「法律/法规」类节点 %d 个；样例：%s"
          % (len(law_nodes), json.dumps(law_nodes[:3], ensure_ascii=False)[:300]))
    ab = [e for e in edges if "废止" in json.dumps(e, ensure_ascii=False)]
    print("  含「废止」的边 %d 条" % len(ab))
    for e in ab[:5]:
        print("   · %s" % json.dumps(e, ensure_ascii=False)[:200])

    print("\n==== 4) 站点怎么加载图谱（决定能否「改 JSON + 重启」）====")
    hits = []
    for p in SITE.rglob("*.py"):
        if "node_modules" in str(p) or ".venv" in str(p):
            continue
        try:
            t = io.open(p, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if "kg_data" in t or "graph_full" in t:
            hits.append(p)
    print("  引用 kg_data/graph_full 的 py 文件：%d 个" % len(hits))
    for p in hits[:10]:
        t = io.open(p, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r"^.*(kg_data|graph_full).*$", t, re.M):
            print("   · %s:%d  %s" % (p.relative_to(SITE), t[:m.start()].count("\n") + 1,
                                      m.group(0).strip()[:120]))
            break

    print("\n==== 5) 有没有构建脚本 / 依赖（决定重建代价）====")
    for pat in ("*kg*", "*图谱*", "*graph*"):
        for p in list(SITE.rglob(pat))[:10]:
            if p.is_file() and "node_modules" not in str(p):
                print("   · %s" % p.relative_to(SITE))
    print("\n  kg_data 目录下的其它文件（看有没有构建产物/统计）：")
    for p in sorted(KG.rglob("*"))[:20] if KG.is_dir() else []:
        print("   · %s" % p.relative_to(KG))

    print("\n==== 6) 站点里跟图谱有关的接口 ====")
    for p in SITE.rglob("*.py"):
        if ".venv" in str(p):
            continue
        t = io.open(p, encoding="utf-8", errors="ignore").read()
        for m in re.finditer(r'@\w+\.(?:get|post)\("([^"]*(?:kg|graph|图谱|实体|推荐)[^"]*)"', t):
            print("   · %s → %s" % (p.relative_to(SITE), m.group(1)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
