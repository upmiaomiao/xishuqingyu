#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""示例题库界面契约检查：前端要的东西，后端与静态资源必须真的给。

照 `查生成界面契约.py` 的做法 —— 但这次查的是**静态契约**：
  ① 题库 JSON 真的能通过 /static 取到（最容易忘的就是 routes.py 白名单那一行，
     忘了就是 404，面板只会显示"题库暂时读不出来"，不报错、不崩，很容易漏掉）；
  ② JSON 结构与条数对得上（焚烧 32 / 固废 39）；
  ③ **没有内部评测信息泄漏**（来源、效果证据、训练集、judge、heldout… 一个都不许有）；
  ④ 没有英文题干残留、没有康熙部首之类的错码位字；
  ⑤ 入口在新对话那一屏（message.js 的欢迎页模板里），输入框那边已经撤掉；浮层是 position:fixed
     且有 `[hidden]` 覆盖 —— 少这条覆盖，面板打开后就再也收不起来；
  ⑥ JS 里 el('…') 引用的每个 id 都有宿主（index.html 或 JS 拼出来的 HTML）；
  ⑦ 缺陷注入：查一个没登记的路径必须取不到 —— 证明 ① 的通过不是因为白名单形同虚设。

用法（服务器）：python3 查题库契约.py
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8011"
SITE = "/home/test/xishu_qingyu_serve"
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + detail) if detail else ""))


def fetch(path: str):
    """→ (状态码, 文本)。非 200 不抛异常，交给断言去判。"""
    try:
        with urllib.request.urlopen(BASE + path, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:                                   # 连不上：算失败，不当成 404
        return 0, str(e)


def main() -> int:
    print("=" * 60)

    print("[1] 题库 JSON 能取到并解析")
    st, body = fetch("/static/data/question-bank.json")
    check("GET /static/data/question-bank.json 200", st == 200, "状态 %s" % st)
    try:
        data = json.loads(body)
    except Exception as e:
        check("JSON 可解析", False, str(e)[:90])
        return 1
    check("JSON 可解析", True)

    tabs = data.get("tabs", [])
    check("有 2 个一级分类（垃圾焚烧 / 固废）", len(tabs) == 2,
          "、".join(t.get("name", "?") for t in tabs))
    counts = {t["name"]: {g["name"]: len(g["items"]) for g in t["groups"]} for t in tabs}
    n_burn = sum(counts.get("垃圾焚烧", {}).values())
    n_waste = sum(counts.get("固废", {}).values())

    print("[2] 结构与条数")
    want_burn = {"项目准入与环保合规决策": 16, "技术路线与方案编制决策": 5,
                 "现场运行与异常处置决策": 2, "趋势复盘与数据沟通决策": 9}
    want_waste = {"专业展示案例 · 简单": 5, "专业展示案例 · 中等": 3,
                  "专业展示案例 · 困难": 11, "日常问题展示": 20}
    check("焚烧四类条数正确", counts.get("垃圾焚烧") == want_burn, str(counts.get("垃圾焚烧")))
    check("固废四类条数正确", counts.get("固废") == want_waste, str(counts.get("固废")))
    check("焚烧合计 32 条", n_burn == 32, "%d 条" % n_burn)
    check("固废合计 39 条（13 条困难里已去重 2 条）", n_waste == 39, "%d 条" % n_waste)

    items = [q for t in tabs for g in t["groups"] for q in g["items"]]
    check("每题都是非空字符串", all(isinstance(q, str) and q.strip() for q in items))
    check("没有完全重复的题干", len({re.sub(r"\W", "", q) for q in items}) == len(items),
          "%d 条 / 去重后 %d 条" % (len(items), len({re.sub(r"\W", "", q) for q in items})))

    print("[3] 内部评测信息不得出现在给客户看的数据里")
    leak_words = ["来源：", "效果证据", "训练集", "黄金样本", "sft3", "accepted", "judge",
                  "heldout", "family=", "golden", "工艺域", "画补", "type=wte", "判分"]
    leaked = [(w, q[:30]) for q in items for w in leak_words if w in q]
    check("无内部评测口径残留（%d 个关键词）" % len(leak_words), not leaked, str(leaked[:3]))

    print("[4] 题干文字质量")
    check("无英文原文残留", not [q for q in items if q.startswith("You are")],
          str([q[:40] for q in items if q.startswith("You are")][:2]))
    suspicious = [c for q in items for c in q
                  if 0x2E80 <= ord(c) <= 0x2FDF or 0x3400 <= ord(c) <= 0x4DBF]
    check("无康熙部首/扩展区错码位字", not suspicious, "、".join(sorted(set(suspicious))[:6]))

    print("[5] 前端资源与模块")
    st_h, html = fetch("/")
    check("GET / 200", st_h == 200, "状态 %s" % st_h)
    st_js, js = fetch("/static/js/questions.js")
    check("GET /static/js/questions.js 200（已登记进白名单）", st_js == 200, "状态 %s" % st_js)
    st_m, main_js = fetch("/static/js/main.js")
    check("main.js 引入了题库模块并初始化",
          st_m == 200 and "initQuestionBank" in main_js, "状态 %s" % st_m)
    st_msg, msg_js = fetch("/static/js/message.js")
    check("欢迎页里有题库入口（入口在新对话这一屏，不在输入框）",
          st_msg == 200 and 'id="qbToggle"' in msg_js, "状态 %s" % st_msg)
    check("输入框那一份入口确实撤掉了（首页 HTML 里没有 qbToggle/qbPanel）",
          'id="qbToggle"' not in html and 'id="qbPanel"' not in html)
    check("浮层骨架由 questions.js 建、挂到 body（不随聊天区重渲染被销毁）",
          "document.body.appendChild(panel)" in js and "qb-panel" in js)
    check("已去掉「点一条直接发给模型」那句提示",
          "点一条直接发给模型" not in msg_js and "点一条直接发给模型" not in html)
    # 欢迎页停着不动时每 10 秒换一组（用户要求「默认 10 秒换一次问题」）
    check("示例问题每 10 秒自动轮换（周期写在 message.js 里）",
          "WELCOME_ROTATE_MS = 10000" in msg_js and "setInterval" in msg_js)
    check("聊起来之后轮换定时器会停（不在后台空转）",
          "stopWelcomeRotation" in msg_js and "rotateWelcomeExamples" in msg_js)
    # 鼠标停在示例区上暂停轮换（否则快到点时点下去会点到被换掉的那一道）
    check("鼠标停在示例区上会暂停轮换", "mouseenter" in msg_js and "welcomePaused" in msg_js)
    # 用户报的 bug：「我居然可以一直新建对话」—— 空对话要复用，不能越点越多
    st_s, store_js = fetch("/static/js/store.js")
    check("空对话不再越点越多（newConversation 会复用空壳）",
          st_s == 200 and "isPristine(cur)" in store_js, "状态 %s" % st_s)
    check("加载时把多余空壳裁掉、有内容的会话不动",
          "keptEmpty" in store_js and "state.chats.filter" in store_js)

    st_c, css = fetch("/static/app.css")
    check("GET /static/app.css 200", st_c == 200, "状态 %s" % st_c)
    for cls in (".qb-panel", ".qb-row", ".qb-full", ".qb-entry"):
        check("app.css 含 %s" % cls, st_c == 200 and cls in css)
    blk = css.split(".qb-panel {", 1)[1].split("}", 1)[0] if ".qb-panel {" in css else ""
    check("浮层用 position:fixed（点别处收起的浮层行为）", "position:fixed" in blk)
    # display:flex 会盖掉 hidden 属性 —— 少了这条覆盖，面板打开后就再也收不起来
    check("浮层有 .qb-panel[hidden] 覆盖", ".qb-panel[hidden]" in css)

    print("[6] JS 引用的 id 都有宿主")
    ids = sorted(set(re.findall(r"el\('([A-Za-z0-9_]+)'\)", js)) |
                 set(re.findall(r"getElementById\('([A-Za-z0-9_]+)'\)", js)))
    # 宿主可能写在 index.html 里，也可能是 JS 拼出来的 HTML（欢迎页入口就在 message.js 里）
    hay = html + msg_js
    missing = [i for i in ids if ('id="%s"' % i) not in hay]
    check("引用 %d 个 id 都有宿主" % len(ids), not missing, str(missing))

    print("[7] 缺陷注入：没登记的路径必须取不到")
    st_bad, _ = fetch("/static/data/question-bank.json.bak")
    check("未登记路径取不到（证明白名单有效）", st_bad != 200, "状态 %s" % st_bad)

    print("=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：" + b)
    return 1 if BAD else 0


if __name__ == "__main__":
    raise SystemExit(main())
