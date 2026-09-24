# -*- coding: utf-8 -*-
"""只读：只看"材料自身"的块（按 source 过滤），不看引用它的报告块。
再查 GB3095-2012/固废法 自身有没有被标『已废止』，以及江苏太湖地标在不在。
"""
import io
import json
import re

CH = "/data/fagui_rag/index/chunks.jsonl"

# 只关心这些"材料自身"的 source 特征
OWN = {
    "GB3095-2012 自身": re.compile(r"GB\s*3095[—\-–]2012"),
    "GB3095-2026 自身": re.compile(r"GB\s*3095[—\-–]2026"),
    "固废法自身": re.compile(r"固体废物污染环境防治法"),
    "环评法自身": re.compile(r"环境影响评价法"),
    "法典自身": re.compile(r"生态环境法典"),
}
DB32 = re.compile(r"DB32|太湖地区城镇污水处理厂|太湖流域")

own = {k: {} for k in OWN}
own_ex = {k: [] for k in OWN}
db32 = []
n = 0
with io.open(CH, encoding="utf-8", errors="replace") as f:
    for line in f:
        n += 1
        try:
            o = json.loads(line)
        except Exception:
            continue
        src = o.get("source") or ""
        st = o.get("status") or ""
        title = (o.get("title") or "")[:50]
        for k, rx in OWN.items():
            if rx.search(src):                     # ← 只看 source（材料自身）
                own[k][st or "(空)"] = own[k].get(st or "(空)", 0) + 1
                if len(own_ex[k]) < 3:
                    own_ex[k].append((st or "(空)", title, src[:96]))
        if DB32.search(src) or DB32.search(title):
            if len(db32) < 12:
                db32.append((st or "(空)", title, src[:90]))

print("总块数:", n)
print("\n=== 材料自身（按 source 命中）的 status 分布 ===")
for k in OWN:
    tot = sum(own[k].values())
    print("  %-18s 共 %5d 块   %s" % (k, tot, dict(sorted(own[k].items(), key=lambda x: -x[1]))))
    for st, title, src in own_ex[k][:2]:
        print("        · [%s] %s | %s" % (st, title, src))

print("\n=== 江苏太湖地方标准（source/标题命中 DB32/太湖地区城镇污水处理厂/太湖流域）===")
if not db32:
    print("   没有命中")
for st, title, src in db32:
    print("   · [%s] %s | %s" % (st, title, src))
