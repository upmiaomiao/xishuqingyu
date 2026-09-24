#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""摸清线上知识图谱的真实结构 —— 中文化映射必须照着实据写，不能猜。

要拿到三样东西：
  1. 所有 label（节点类型）及其数量  → 图例中文化用
  2. 所有出现过的属性键 + 样例值      → 详情栏中文化用（name_zh / level / …）
  3. 所有关系名（rel）                → 关系路径中文化用（HAS_ARTICLE / …）
"""
from __future__ import annotations

import collections
import json
import sys
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


print("=" * 96)
print("① /kg/stats 的 label 分布（图例中文化用）")
print("=" * 96)
st = get("/kg/stats")
print(json.dumps({k: v for k, v in st.items() if k != "labels"}, ensure_ascii=False)[:400])
labels = st.get("labels") or {}
for k, v in sorted(labels.items(), key=lambda x: -x[1]):
    print("  %-22s %6d" % (k, v))

print()
print("=" * 96)
print("② 抓一批子图，统计属性键与关系名（详情栏 / 关系路径中文化用）")
print("=" * 96)

queries = ["中华人民共和国固体废物污染环境防治法", "危险废物", "生态环境部", "生活垃圾焚烧",
           "排污许可", "河北省", "唐山市", "大气污染物", "水泥", "钢铁",
           "焚烧炉", "烟气", "颗粒物", "二氧化硫", "生态环境局", "排污许可证"]

prop_keys: collections.Counter = collections.Counter()
prop_sample: dict[str, list[str]] = collections.defaultdict(list)
rel_names: collections.Counter = collections.Counter()
label_of_key: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
edge_sample: list[str] = []

for q in queries:
    try:
        # limit 上限受后端 KG_MAX_SUBGRAPH_NODES 约束，200 会 422。
        # 前端用的是 70，这里保持一致。
        d = get("/kg/search?query=%s&depth=2&limit=70" % urllib.parse.quote(q))
    except Exception as e:                                        # noqa: BLE001
        print("  查询失败 %s：%s" % (q, e))
        continue
    for n in d.get("nodes", []):
        lab = n.get("label", "?")
        for k, v in (n.get("props") or {}).items():
            prop_keys[k] += 1
            label_of_key[k][lab] += 1
            if len(prop_sample[k]) < 4 and str(v) not in prop_sample[k]:
                prop_sample[k].append(str(v)[:60])
    for e in d.get("links", []):
        rel_names[e.get("type", "?")] += 1
        if len(edge_sample) < 8:
            edge_sample.append("%s --%s--> %s" % (e.get("source", "")[:26],
                                                  e.get("type"), e.get("target", "")[:26]))

print("属性键（共 %d 种）：" % len(prop_keys))
for k, c in prop_keys.most_common():
    labs = ",".join("%s×%d" % (a, b) for a, b in label_of_key[k].most_common(3))
    print("  %-22s %5d 次   出现在：%s" % (k, c, labs))
    for s in prop_sample[k][:3]:
        print("        · %s" % s)

print()
print("关系名（共 %d 种）：" % len(rel_names))
for k, c in rel_names.most_common():
    print("  %-28s %5d" % (k, c))

print()
print("关系样例：")
for s in edge_sample:
    print("  " + s)
