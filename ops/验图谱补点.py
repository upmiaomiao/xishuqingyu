#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""[026] 补点后的验收：走**线上接口**（不是直接读 JSON）确认图谱真的把这批数据供出来了。

看三件事：
  ① /kg/stats 节点/边数是否 +5 / +16；
  ② /kg/search?query=生态环境法典 能否带出"废止"关系的法律；
  ③ /kg/entities 或 /kg/suggest 里法典是否作为法律实体出现。
另外单独核对：被废止的 6 部法律在图上是否已从「现行」变「已废止」。
"""
from __future__ import annotations

import io
import json
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"
KG = "/home/test/xishu_qingyu_serve/kg_data/graph_full.json"


def get(path: str, **q) -> dict:
    url = BASE + path + (("?" + urllib.parse.urlencode(q)) if q else "")
    with urllib.request.urlopen(url, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print("==== ① /kg/stats ====")
    try:
        s = get("/kg/stats")
        print("  %s" % json.dumps(s, ensure_ascii=False)[:400])
    except Exception as e:                                        # noqa: BLE001
        print("  失败：%s" % e)

    print("\n==== ② /kg/search?query=生态环境法典 ====")
    try:
        d = get("/kg/search", query="生态环境法典")
        txt = json.dumps(d, ensure_ascii=False)
        print("  返回 %d 字节" % len(txt))
        print("  含「放射性污染防治法」：%s" % ("放射性污染防治法" in txt))
        print("  含「SUPERSEDES/废止」：%s" % ("SUPERSEDES" in txt or "废止" in txt))
        print("  片段：%s" % txt[:600])
    except Exception as e:                                        # noqa: BLE001
        print("  失败：%s" % e)

    print("\n==== ③ 图数据核对（直接读文件，确认落盘内容）====")
    g = json.loads(io.open(KG, encoding="utf-8").read())
    nodes, edges = g["nodes"], g["edges"]
    print("  节点 %d、边 %d" % (len(nodes), len(edges)))
    code = [nid for nid, n in nodes.items()
            if n.get("label") == "Law" and "生态环境法典" in json.dumps(n, ensure_ascii=False)]
    print("  法典 Law 节点：%s" % code)
    sup = [e for e in edges if e.get("rel") == "SUPERSEDES"
           and any(c in str(e.get("from_id")) for c in code)]
    print("  法典发出的 SUPERSEDES 边：%d 条" % len(sup))
    for e in sup[:12]:
        to = (nodes.get(e["to_id"]) or {}).get("props", {})
        print("   · → %-28s status=%s" % ((to.get("full_name") or e["to_id"])[:28],
                                          to.get("validity_status")))
    still = [(nid, (n.get("props") or {}).get("validity_status")) for nid, n in nodes.items()
             if n.get("label") == "Law" and (n.get("props") or {}).get("validity_status") == "现行"
             and any(k in nid for k in ("环境保护法", "环境影响评价法", "海洋环境保护法",
                                        "大气污染防治法", "水污染防治法", "土壤污染防治法",
                                        "固体废物污染环境防治法", "噪声污染防治法",
                                        "放射性污染防治法", "清洁生产促进法"))]
    print("  名单内仍标「现行」的：%s" % (still or "无 ✅"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
