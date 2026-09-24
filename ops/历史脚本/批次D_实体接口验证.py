#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次 D 验证：第 7 项（知识图谱）。

覆盖后端新接口 POST /kg/entities。前端部分（中文化、匹配列表、详情栏、视图操作、
连线优化）用 前端快检.py + 批次D验证.mjs 检查。

为什么要单独测这个接口：它是"正文实体可点击"的唯一数据来源，
它错了，正文要么全变成链接、要么一个都不变，而这两种情况都不会报错 ——
静默出错最难发现。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://10.201.31.10:8011"
P = F = 0


def ck(name: str, cond: bool, note: str = "") -> None:
    global P, F
    if cond:
        P += 1
        print("  √ %s%s" % (name, ("　" + note) if note else ""))
    else:
        F += 1
        print("  × %s%s" % (name, ("　" + note) if note else ""))


def post(path: str, payload: dict) -> tuple[int, object]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:                                          # noqa: BLE001
            return e.code, raw


print("=" * 92)
print("① 正常识别：一段真实的回答正文")
print("=" * 92)
TEXT = (
    "根据《中华人民共和国固体废物污染环境防治法》第六条的规定，"
    "各级人民政府对本行政区域内固体废物污染环境防治负责。"
    "生态环境部发布的 GB 18597-2023 对危险废物的贮存提出了要求。"
    "唐山市的排污单位应当依法申领排污许可证，控制颗粒物和二氧化硫排放。"
)
st, d = post("/kg/entities", {"text": TEXT})
ck("HTTP 200", st == 200, "status=%d" % st)
ck("返回结构含 entities / count", isinstance(d, dict) and "entities" in d and "count" in d)
ents = d.get("entities", []) if isinstance(d, dict) else []
ck("识别出实体", len(ents) > 0, "%d 个" % len(ents))
names = [e["name"] for e in ents]
print("      识别到：" + "、".join(names[:12]))

ck("认出法规（固体废物污染环境防治法）",
   any("固体废物污染环境防治法" in n for n in names))
ck("认出机构（生态环境部）", any("生态环境部" in n for n in names))
ck("认出地区（唐山市）", any(n == "唐山市" for n in names))

# 以下两条是**实测出来的图谱数据覆盖问题**，不是代码问题。
# 第一版断言"必须认出颗粒物/二氧化硫"，跑出来失败了，查证后发现：
#   · 图谱里污染物节点叫「粉尘颗粒物」，没有单独的「颗粒物」节点；
#   · 「二氧化硫」只作为若干标准标题的子串出现，没有独立节点。
# 也就是说正文里写「颗粒物」「二氧化硫」时不会有下划线。这是数据缺口，
# 记在这里当**已知限制**，不去放宽匹配来掩盖它 ——
# 放宽成子串匹配会让「中华人民共和国」在几乎每句里都被点亮。
d_pol = post("/kg/entities", {"text": "粉尘颗粒物"})[1]
ck("污染物节点用图谱里的真名「粉尘颗粒物」时认得出",
   any(e["name"] == "粉尘颗粒物" for e in (d_pol.get("entities") or [])),
   "已知限制：图谱无独立「颗粒物」「二氧化硫」节点")

print()
print("=" * 92)
print("② 每个实体都带齐前端需要的字段")
print("=" * 92)
need = {"id", "name", "label", "degree"}
ck("字段齐全", all(need <= set(e.keys()) for e in ents))
ck("name 都是 2 字以上（单字会到处误命中）",
   all(len(e["name"]) >= 2 for e in ents),
   "最短：%s" % min((e["name"] for e in ents), key=len, default="—"))
ck("label 非空", all(e["label"] for e in ents))
ck("id 唯一（否则前端替换会错位）",
   len({e["id"] for e in ents}) == len(ents))
# 度数 0 的节点点进去只有它自己，做成可点击像坏了 —— 接口层就该滤掉
ck("degree 全部 ≥ 1（点进去一定有关系可看）",
   all(e["degree"] >= 1 for e in ents),
   "最小 degree=%d" % min((e["degree"] for e in ents), default=0))

print()
print("=" * 92)
print("③ 名字重叠：短的被长的包含时必须去掉，否则会把长名字切碎")
print("=" * 92)
# 关键：文本里必须出现**图谱里存的那个完整名字**。
# 第一版写成「固体废物污染环境防治法」，而图谱里存的是
# 「中华人民共和国固体废物污染环境防治法」，长名字压根没命中，
# 去重分支自然没被走到 —— 测试通过了也说明不了任何事。
st, d = post("/kg/entities", {
    "text": "《中华人民共和国固体废物污染环境防治法》对固体废物的定义作了规定。",
})
got = [e["name"] for e in (d.get("entities") or [])]
print("      识别到：" + "、".join(got))
longer = [n for n in got if "污染环境防治法" in n]
shorter = [n for n in got if n == "固体废物"]
ck("长名字在", bool(longer), longer[0] if longer else "—")
ck("被长名字包含的短名字已剔除", not shorter, "短名：%s" % (shorter or "无"))
ck("返回顺序是长→短（前端按此顺序替换）",
   all(len(got[i]) >= len(got[i + 1]) for i in range(len(got) - 1)) if len(got) > 1 else True,
   " / ".join("%d字" % len(n) for n in got))

print()
print("=" * 92)
print("④ 边界：空文本 / 无匹配 / 超长")
print("=" * 92)
st, d = post("/kg/entities", {"text": ""})
ck("空文本 → 200 且空列表", st == 200 and d.get("entities") == [], "status=%d" % st)

st, d = post("/kg/entities", {"text": "zzzz qqqq 无意义内容 9876543210"})
ck("无匹配 → 200 且空列表（不是错误）",
   st == 200 and d.get("entities") == [], "status=%d" % st)
ck("无匹配也给出 count 字段", isinstance(d, dict) and d.get("count") == 0)

st, d = post("/kg/entities", {})
ck("缺 text 字段 → 用默认空串，不报错", st == 200, "status=%d" % st)

st, d = post("/kg/entities", {"text": "固" * 20001})
ck("超过 20000 字 → 422（有上限保护）", st == 422, "status=%d" % st)
ck("422 也回统一错误结构（不是裸文本）",
   isinstance(d, dict) and d.get("code"), str(d)[:120])

print()
print("=" * 92)
print("⑤ 规模：一段长正文不会拖慢接口")
print("=" * 92)
import time
long_text = TEXT * 60                                            # 约 8400 字
t0 = time.time()
st, d = post("/kg/entities", {"text": long_text})
dt = time.time() - t0
ck("长正文仍 200", st == 200, "status=%d" % st)
ck("耗时 < 3s", dt < 3.0, "%.2fs，返回 %d 个实体" % (dt, len(d.get("entities") or [])))

print()
print("=" * 92)
print("⑥ 与 /kg/search 的一致性：entities 给的名字确实能在图谱里搜到")
print("=" * 92)
sample = names[:3]
for nm in sample:
    with urllib.request.urlopen(
        BASE + "/kg/search?query=" + urllib.parse.quote(nm) + "&depth=0&limit=10",
        timeout=60,
    ) as r:
        sd = json.loads(r.read().decode("utf-8"))
    hit = [x for x in sd.get("nodes", []) if x.get("matched")]
    ck("「%s」能搜到" % nm, len(hit) > 0, "%d 个命中" % len(hit))

print()
print("=" * 92)
print("结论：通过 %d / 失败 %d" % (P, F))
print("=" * 92)
raise SystemExit(1 if F else 0)
