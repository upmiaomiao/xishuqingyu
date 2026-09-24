#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""线上验收探针：检索层改造后，直接问网站，看引用和回答是否都对得上。

验收点（每条都带反向检查）：
  ① I 类场防渗 —— 必须引到 GB 18599-2020，且回答里出现 1.0×10⁻⁵ 这个数值
  ② 二噁英限值 —— 必须引到标准（不再是清一色环评报告），回答里出现限值/毒性当量
  ③ 济宁项目案例 —— 反向：必须仍然引到该项目的环评报告（别把案例问题也弄坏）
  ④ 排污许可证有效期 —— 必须引到《排污许可管理条例》，回答出现"5年"
"""
from __future__ import annotations

import json
import re
import urllib.request

BASE = "http://10.201.31.10:8011"
AUTH = ("生态环境标准规范", "生态环境法律法规", "环评导则")

CASES = [
    {
        "q": "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
        "need_cite": "GB 18599",
        "answer_pat": r"1\.0\s*[×x]\s*10|10\s*[-−⁻^]\s*5|10-5",
        "desc": "回答要给出 I 类场防渗的渗透系数数值",
    },
    {
        "q": "二噁英的排放限值是多少？",
        "need_cite": "标准",
        "answer_pat": r"ng|TEQ|0\.1|0\.5|毒性当量",
        "desc": "回答要给出二噁英限值/毒性当量口径",
    },
    {
        "q": "济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？",
        "need_cite": "济宁",
        "answer_pat": r".{20,}",
        "desc": "案例问题必须还能引到项目自己的环评报告（反向断言）",
    },
    {
        "q": "排污许可证的有效期是多久？",
        "need_cite": "排污许可",
        "answer_pat": r"5\s*年|五年",
        "desc": "回答要说清有效期",
    },
]


def ask(q: str) -> dict:
    req = urllib.request.Request(
        BASE + "/hybrid_search",
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode())


ok = fail = 0
def say(cond: bool, msg: str) -> None:
    global ok, fail
    if cond:
        ok += 1; print(f"  ✅ {msg}")
    else:
        fail += 1; print(f"  ❌ {msg}")

for c in CASES:
    print("=" * 104)
    print("Q:", c["q"])
    try:
        d = ask(c["q"])
    except Exception as e:  # noqa: BLE001
        print("  请求失败:", type(e).__name__, str(e)[:200]); fail += 1; continue
    srcs = d.get("sources") or []
    auth = [s for s in srcs if (s.get("source") or "").split("/")[0] in AUTH]
    print(f"  route={d.get('route')}  来源 {len(srcs)} 条，其中依据类 {len(auth)} 条")
    for s in srcs:
        tag = "依据" if (s.get("source") or "").split("/")[0] in AUTH else "案例"
        print(f"    [{s.get('index')}] {tag} {s.get('source')}")
    ans = d.get("answer") or ""
    hit_cite = [s for s in srcs if c["need_cite"] in (s.get("source") or "")]
    say(bool(hit_cite), f"引用里有「{c['need_cite']}」（{len(hit_cite)} 条）")
    say(bool(re.search(c["answer_pat"], ans)), f"回答里命中 {c['answer_pat']} —— {c['desc']}")
    print("  回答节选:", re.sub(r"\s+", " ", ans)[:300])

print(f"\n==== 线上验收：通过 {ok} / 失败 {fail} ====")
