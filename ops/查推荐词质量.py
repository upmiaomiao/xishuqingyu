#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把前端"推荐关键词"那一排**原样**打出来，判断质量。

前端 renderKgSuggest 的逻辑是：把所有类型的 examples 合起来，
按 degree 降序取前 14 个。所以这里照做，看用户第一眼看到的是什么词。
"""
import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8011"

with urllib.request.urlopen(BASE + "/kg/suggest?per_label=4", timeout=30) as r:
    d = json.loads(r.read().decode("utf-8"))

types = d["types"]

# 照抄前端 renderKgSuggest 的**轮转**取词逻辑：每类取第 r 个，r 从 0 递增。
# 第一版是按度数全局排序，实测前 14 个全被 Organization/Standard/Region 占满，
# 污染物、法律、行业、案例一个都进不来 —— 用户要的是"这里都有些什么"。
flat = []
for r in range(4):
    for t in types:
        ex = t["examples"]
        if r < len(ex):
            flat.append((ex[r]["degree"], ex[r]["name"], t["label"]))
        if len(flat) >= 14:
            break
    if len(flat) >= 14:
        break

print("=== 前端「推荐关键词」实际会显示的 14 个（跨类型轮转）===")
seen_types = []
for i, (deg, name, label) in enumerate(flat, 1):
    if label not in seen_types:
        seen_types.append(label)
    flag = ""
    if name.startswith("Article_"):
        flag = "   ★ 看起来像节点 id，不是人话"
    elif len(name) > 30:
        flag = "   ★ 太长（%d 字，前端会截断显示）" % len(name)
    print("  %2d. [%-14s] %-40s 度=%-4d%s" % (i, label, name[:40], deg, flag))
print()
print("  覆盖了 %d 种类型：%s" % (len(seen_types), "、".join(seen_types)))

print()
print("=== 全部类型 × 例子（用户点「按类型浏览」看到的）===")
for t in types:
    print("  [%s / %s] %d 个" % (t["label"], t["count"], len(t["examples"])))
    for e in t["examples"]:
        flag = ""
        if e["name"].startswith("Article_"):
            flag = "  ★ 像 id"
        elif len(e["name"]) > 34:
            flag = "  ★ 太长"
        print("       度=%-4d %s%s" % (e["degree"], e["name"][:60], flag))

print()
print("=== 统计：有多少名字是回退成节点 id 的 ===")
allnames = [e["name"] for t in types for e in t["examples"]]
idlike = [n for n in allnames if "_" in n and n.split("_")[0] in
          ("Article", "Document", "Law", "Standard", "Case", "Pollutant",
           "Organization", "Region", "Industry", "Violation", "Penalty",
           "Regulation", "TreatmentTech", "PollutionSource")]
print("  例子总数 %d，其中疑似回退成 id 的 %d 个：%s" % (len(allnames), len(idlike), idlike))

print()
print("=== Article 节点到底有没有名字属性 ===")
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
from xishu_pipeline.config import KG_PATH
payload = json.loads(open(KG_PATH, encoding="utf-8").read())
nodes = payload.get("nodes", {})
n_art = 0
sample = []
for nid, n in nodes.items():
    if n.get("label") == "Article":
        n_art += 1
        if len(sample) < 6:
            sample.append((nid, sorted((n.get("props") or {}).keys())))
print("  Article 节点共 %d 个" % n_art)
for nid, keys in sample:
    print("    %-46s props 键=%s" % (nid[:46], keys))

print()
print("=== 顶层属性键分布（各类型都有什么字段）===")
from collections import Counter
keyc = Counter()
for n in nodes.values():
    for k in (n.get("props") or {}):
        keyc[k] += 1
for k, v in keyc.most_common(20):
    print("    %-22s %d 个节点有" % (k, v))
