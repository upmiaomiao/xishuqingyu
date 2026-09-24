# -*- coding: utf-8 -*-
"""只读：逐块核对索引里这批材料的 title/status/source，判断是"没入库"还是"入库了但状态/排序有问题"。

chunks.jsonl 435MB / 265,317 块 —— 流式扫一遍，不载入内存。
"""
import io
import json
import re

CH = "/data/fagui_rag/index/chunks.jsonl"

PROBES = {
    "法典1242条": re.compile(r"第一千二百四十二条"),
    "法典标题": re.compile(r"生态环境法典"),
    "固废法": re.compile(r"固体废物污染环境防治法"),
    "环评法": re.compile(r"环境影响评价法"),
    "GB3095-2026": re.compile(r"GB\s*3095[—\-–]2026"),
    "GB3095-2012": re.compile(r"GB\s*3095[—\-–]2012"),
    "过渡阶段": re.compile(r"过渡阶段"),
    "GB8978第一类": re.compile(r"第一类污染物"),
    "DB32/1072": re.compile(r"DB32[/\s]*1072|太湖地区城镇污水处理厂"),
}

hit = {k: [] for k in PROBES}
cnt = {k: 0 for k in PROBES}
status_of = {}          # 探针 → status 分布
n = 0
with io.open(CH, encoding="utf-8", errors="replace") as f:
    for line in f:
        n += 1
        try:
            o = json.loads(line)
        except Exception:
            continue
        st = o.get("status") or (o.get("meta") or {}).get("status") or ""
        title = o.get("title") or o.get("name") or ""
        src = o.get("source") or ""
        text = (title + " " + src + " " + (o.get("text") or "")[:1200])
        for k, rx in PROBES.items():
            if rx.search(text) or rx.search(src):
                cnt[k] += 1
                status_of.setdefault(k, {})
                status_of[k][st or "(空)"] = status_of[k].get(st or "(空)", 0) + 1
                if len(hit[k]) < 4:
                    hit[k].append((st or "(空)", title[:56], src[:70],
                                   (o.get("text") or "")[:90].replace("\n", " ")))

print("总块数:", n)
for k in PROBES:
    print("\n=== %s ：%d 块 ===" % (k, cnt[k]))
    if status_of.get(k):
        print("   status 分布:", dict(sorted(status_of[k].items(), key=lambda x: -x[1])))
    for st, title, src, txt in hit[k][:3]:
        print("   · [%s] %s" % (st, title))
        print("       source: %s" % src)
        print("       正文: %s" % txt)
