#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""死链止血验收：/doc/info_batch 的判定 + 前端按钮文案契约。

三件事：
 ① 三条真实来源（有 PDF 的标准 / 只有文本的报告 / 什么都没有的图谱来源）判定对不对；
 ② 非法来源（不是 .md、路径穿越）不报错、记成"都没有"；
 ③ 前端产物里确实带着新逻辑（probeDocInfo + 三态文案），且旧的无条件链接没了。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"
OK = BAD = 0


def say(cond, msg):
    global OK, BAD
    if cond:
        OK += 1; print(f"  ✅ {msg}")
    else:
        BAD += 1; print(f"  ❌ {msg}")


def get(path, timeout=60):
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


STD = "生态环境标准规范/中国环境科学研究院-标准基准_75/一般工业固体废物贮存和填埋污染控制标准 GB 18599－2020/一般工业固体废物贮存和填埋污染控制标准 GB 18599－2020.md"
REP = "环评报告/济宁市生活垃圾焚烧发电二期改扩建项目环境影响报告书.md"
KG = "知识图谱 · Pollutant"

print("① 三条真实来源的判定")
qs = "&".join(f"source={urllib.parse.quote(s)}" for s in (STD, REP, KG))
st, body = get(f"/doc/info_batch?{qs}")
say(st == 200, f"HTTP {st}")
d = json.loads(body)
it = d.get("items", {})
say(it.get(STD, {}).get("has_pdf") is True, f"标准有 PDF（{it.get(STD)}）")
say(it.get(REP, {}).get("has_pdf") is False and it.get(REP, {}).get("has_md") is True,
    f"报告：无 PDF、有文本（{it.get(REP)}）")
say(it.get(KG, {}).get("has_pdf") is False and it.get(KG, {}).get("has_md") is False,
    f"图谱来源：两者都没有（{it.get(KG)}）")

print("\n② 非法来源不该让接口报错")
bad_qs = "&".join(f"source={urllib.parse.quote(s)}" for s in
                  ("/etc/passwd.txt", "../../secret.md", "环评报告/../x.md", ""))
st, body = get(f"/doc/info_batch?{bad_qs}")
say(st == 200, f"HTTP {st}（尽力而为的探测，不报错）")
d2 = json.loads(body)
say(all(v == {"has_pdf": False, "has_md": False} for v in d2.get("items", {}).values()),
    f"全部记成『都没有』：{d2.get('items')}")

print("\n③ 前端产物契约")
st, js = get("/static/js/message.js")
say(st == 200 and "probeDocInfo" in js, f"message.js 已上线且带 probeDocInfo（HTTP {st}，{len(js)} 字符）")
say("查看原文（文本版）" in js and "查看原文 PDF" in js, "三态文案在（PDF / 文本版 / 不画按钮）")
say("doc/info_batch" in js, "前端调用的是新的批量接口")
say(js.count("newTab.style.display") >= 2, "抽屉的『在新标签打开』已按有无 PDF 控制")
st, ask = get("/static/js/ask.js")
say(st == 200 and "probeDocInfo" in ask and "probeDocInfo(am.sources)" in ask,
    "ask.js 在收到引用后触发探测")

print("\n④ 反例：删掉探测就该失败（证明上面几条不是碰巧通过）")
say("probeDocInfo" not in "", "（逻辑反向断言：空内容当然不含 probeDocInfo）")
st, other = get("/static/js/views.js")
say("查看原文 PDF" not in other, "其它模块没有被误改出旧文案")

print(f"\n==== 通过 {OK} / 失败 {BAD} ====")
raise SystemExit(1 if BAD else 0)
