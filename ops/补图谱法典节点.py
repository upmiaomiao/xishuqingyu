#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[026] 给知识图谱补《生态环境法典》法律实体节点与"废止"边，并把被废止法律的
validity_status 与语料对齐。

为什么这么改（依据都来自实测，不是推测）：
  · 图谱是**普通 JSON + 进程内缓存**（`xishu_pipeline/kg.py::load_knowledge_graph()` 直接
    `json.loads(KG_PATH.read_text())` 进 `_kg_cache`），**启动时不重建** ⇒ 改 JSON + 重启即可生效；
  · 边的词表里**本来就有 `SUPERSEDES`**（1,104 条，props 带 `effective_date`）⇒ 补边是同构的；
  · 法典在图上只有 `Document` + 1 个 `Article` 节点，**没有 Law 节点**；
    第1242条废止的 10 部法律里 6 部有 Law 节点但 `validity_status` 全写「现行」（与语料矛盾），
    4 部（环境保护法/海洋环境保护法/放射性污染防治法/清洁生产促进法）**连节点都没有**。

安全保障：
  · `--dry-run` 先看要改什么（默认就是 dry-run，必须显式 `--apply` 才写盘）；
  · 写盘前备份 `graph_full.json.bak_before_codex_<TS>` 并核对字节数；
  · 只改**第1242条名单内**的节点，名单外的节点一律不碰；
  · 节点 id 用 md5(label|name|盐)[:8]，并检查不与现有 id 冲突；
  · 写入走临时文件 + `os.replace`（原子替换），写完再 json.load 回读校验。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import time
from pathlib import Path

KG = Path("/home/test/xishu_qingyu_serve/kg_data/graph_full.json")
REGION_NAME = "全国"
ORG_NAME = "全国人民代表大会"          # 有就加 ISSUED_BY，没有就不加（绝不自己造机构）

CODE = "中华人民共和国生态环境法典"
CODE_EFFECTIVE = "2026-08-15"
CODE_NOTE = "《中华人民共和国生态环境法典》第一千二百四十二条"
# 第1242条**原文列出**的 10 部（照抄法典原文），附各自施行日（取自各法正文，用于 props.effective_date）
REPEALED = [
    ("中华人民共和国环境保护法", "2015-01-01"),
    ("中华人民共和国环境影响评价法", "2003-09-01"),
    ("中华人民共和国海洋环境保护法", "2024-01-01"),
    ("中华人民共和国大气污染防治法", "2016-01-01"),
    ("中华人民共和国水污染防治法", "2018-01-01"),
    ("中华人民共和国土壤污染防治法", "2019-01-01"),
    ("中华人民共和国固体废物污染环境防治法", "2020-09-01"),
    ("中华人民共和国噪声污染防治法", "2022-06-05"),
    ("中华人民共和国放射性污染防治法", "2003-10-01"),
    ("中华人民共和国清洁生产促进法", "2003-01-01"),
]


def node_name(nid: str, node: dict) -> str:
    p = node.get("props") or {}
    return str(p.get("full_name") or p.get("name") or p.get("name_zh") or "")


def mint(label: str, name: str, taken: set, salt: str = "") -> str:
    """造一个不冲突的节点 id。图谱原 id 尾部的 8 位 hex 反推不出算法（试过 md5/sha1 五种组合），
    所以这里自造：id 只作主键，站点按名称检索，唯一即可。"""
    for i in range(50):
        h = hashlib.md5(("%s|%s|%s|%d" % (label, name, salt, i)).encode("utf-8")).hexdigest()[:8]
        nid = "%s_%s_%s" % (label, name, h)
        if nid not in taken:
            return nid
    raise RuntimeError("id 造不出来（不该发生）")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的写盘（默认只 dry-run）")
    ap.add_argument("--kg", default=str(KG))
    a = ap.parse_args()
    kg = Path(a.kg)
    raw = kg.read_bytes()
    print("图谱：%s（%d 字节）" % (kg, len(raw)))
    g = json.loads(raw.decode("utf-8"))
    nodes, edges = g["nodes"], g["edges"]
    taken = set(nodes)
    print("  现有节点 %d、边 %d" % (len(nodes), len(edges)))

    # ---- 找 Region_全国 与 全国人民代表大会（有就用，没有就跳过）----
    region_id = next((nid for nid, n in nodes.items()
                      if n.get("label") == "Region" and node_name(nid, n) == REGION_NAME), None)
    org_id = next((nid for nid, n in nodes.items()
                   if n.get("label") == "Organization" and ORG_NAME in node_name(nid, n)), None)
    print("  Region_%s → %s；Organization「%s」→ %s"
          % (REGION_NAME, region_id or "（没找到，跳过该边）", ORG_NAME,
             org_id or "（没找到，跳过该边）"))

    add_nodes, add_edges, patches = [], [], []

    # ---- 1) 法典的 Law 节点（原来只有 Document，没有法律实体）----
    code_id = next((nid for nid, n in nodes.items()
                    if n.get("label") == "Law" and CODE in node_name(nid, n)), None)
    if code_id:
        print("  法典 Law 节点已存在：%s（跳过新增）" % code_id)
    else:
        code_id = mint("Law", CODE, taken, "codex")
        taken.add(code_id)
        add_nodes.append((code_id, {
            "label": "Law",
            "props": {"full_name": CODE, "level": "国家", "region": REGION_NAME,
                      "effective_date": CODE_EFFECTIVE, "validity_status": "现行",
                      "summary": "2026-08-15 施行；第1242条同时废止环境保护法等十部法律"},
        }))
        print("  ＋ 新增法典 Law 节点：%s" % code_id)

    # ---- 2) 法典的属地边（有 Region_全国 才加）----
    if region_id and not any(e.get("from_id") == code_id and e.get("rel") == "APPLIES_TO_REGION"
                             and e.get("to_id") == region_id for e in edges):
        add_edges.append((code_id, "Law", "APPLIES_TO_REGION", region_id, "Region", {}))
    if org_id and not any(e.get("from_id") == code_id and e.get("rel") == "ISSUED_BY"
                          and e.get("to_id") == org_id for e in edges):
        add_edges.append((code_id, "Law", "ISSUED_BY", org_id, "Organization", {}))

    # ---- 3) 十部被废止法律：缺节点的补节点、有节点的改状态；两者都补 SUPERSEDES 边 ----
    for law, eff in REPEALED:
        hit = [(nid, n) for nid, n in nodes.items()
               if n.get("label") == "Law" and (law == node_name(nid, n) or law in nid)]
        if hit:
            nid, n = hit[0]
            props = n.setdefault("props", {})
            if str(props.get("validity_status") or "") != "已废止":
                patches.append((nid, "validity_status", props.get("validity_status"), "已废止"))
                props["validity_status"] = "已废止"
            if not props.get("status_note"):
                patches.append((nid, "status_note", "", CODE_NOTE + "：本法同时废止"))
                props["status_note"] = CODE_NOTE + "：本法同时废止"
            print("  ↻ 已有节点改状态：%s（%s）" % (nid, props.get("validity_status")))
        else:
            nid = mint("Law", law, taken, "codex")
            taken.add(nid)
            add_nodes.append((nid, {
                "label": "Law",
                "props": {"full_name": law, "level": "国家", "region": REGION_NAME,
                          "effective_date": eff, "validity_status": "已废止",
                          "status_note": CODE_NOTE + "：本法同时废止"},
            }))
            print("  ＋ 新增被废止法律节点：%s" % nid)

        if not any(e.get("from_id") == code_id and e.get("rel") == "SUPERSEDES"
                   and e.get("to_id") == nid for e in edges):
            add_edges.append((code_id, "Law", "SUPERSEDES", nid, "Law",
                              {"effective_date": "2026年8月15日", "note": CODE_NOTE}))
        if region_id and not any(e.get("from_id") == nid and e.get("rel") == "APPLIES_TO_REGION"
                                 and e.get("to_id") == region_id for e in edges):
            add_edges.append((nid, "Law", "APPLIES_TO_REGION", region_id, "Region", {}))

    print("\n小结：新增节点 %d、改属性 %d 处、新增边 %d"
          % (len(add_nodes), len(patches), len(add_edges)))
    for nid, k, o, n in patches:
        print("   · %s：%s  %r → %r" % (nid, k, o, n))

    if not a.apply:
        print("\n【dry-run】未写盘。要真写：加 --apply")
        return 0

    ts = time.strftime("%Y%m%d_%H%M%S")
    bak = kg.with_name(kg.name + ".bak_before_codex_" + ts)
    shutil.copy2(kg, bak)
    if bak.stat().st_size != len(raw):
        raise SystemExit("备份字节数不一致，中止")
    print("\n备份 → %s（%d 字节，与改前一致）" % (bak, bak.stat().st_size))

    for nid, nd in add_nodes:
        nodes[nid] = nd
    for f, fl, rel, t, tl, pr in add_edges:
        edges.append({"from_id": f, "from_label": fl, "rel": rel,
                      "to_id": t, "to_label": tl, "props": pr})
    out = json.dumps(g, ensure_ascii=False)
    tmp = kg.with_suffix(".json.tmp")
    io.open(tmp, "w", encoding="utf-8", newline="\n").write(out)
    os.replace(tmp, kg)
    g2 = json.loads(kg.read_text(encoding="utf-8"))
    print("写盘完成：节点 %d（+%d）、边 %d（+%d）；回读校验 %s"
          % (len(g2["nodes"]), len(add_nodes), len(g2["edges"]), len(add_edges),
             "✅" if len(g2["nodes"]) == len(nodes) and len(g2["edges"]) == len(edges) else "❌"))
    print("回滚：cp -p %s %s && bash /home/test/安全重启8011.sh" % (bak, kg))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
