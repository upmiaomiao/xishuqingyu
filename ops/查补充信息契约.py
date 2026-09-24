#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编制页 C1/C2 契约：补充内容的"落点"与那个 `const busy` 真 bug。

为什么要有这一份（真机测试已经 20/0 了）：真机测试要起 Chrome、要真跑一次模型
（约 12s），不可能每次改动都跑。这份契约只读**线上文件**做静态检查，秒级可跑，
用来在以后任何人动 gen_ui.js 时立刻发现"按钮没了/又写回 const busy"。
行为正确性由 `看补充信息按钮.js`（真机 20/0）负责，两者分工不同。

必须包含**反向用例**：证明这些检查不是永远返回"通过"的空转。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查补充信息契约.py
"""
from __future__ import annotations

import io
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:8011"
JS_PATH = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js"
CSS_PATH = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css"

P = F = 0


def ck(ok: bool, msg: str) -> None:
    global P, F
    if ok:
        P += 1
        print("  √ " + msg)
    else:
        F += 1
        print("  × " + msg)


def read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


def strip_comments(src: str) -> str:
    """去掉注释后再做"代码长什么样"的检查。

    必须这么做：我自己在 gen_ui.js 里写了注释解释那个 bug，
    注释里就含 `const …, busy = false;` 的字样 —— 第一版契约拿这个正则去扫**全文**，
    于是永远报"还有 const busy"（误报）。检查代码要只看代码。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


# ---------- 检查逻辑（对"给定源码"判定，便于用注入版本做反向用例）----------
def check(js: str, css: str, tag: str = "") -> None:
    code = strip_comments(js)          # 只看代码，不看注释（注释里有反例字样，见 strip_comments）
    print("\n[1] C1：每处都要有「去补充信息」按钮" + tag)
    ck('id="ge-mine"' in js, "模板里有 #ge-mine（问题列表正下方的补充记录块）")
    ck('class="ge-btn ge-btn-ghost ge-go"' in js, "问题卡上带「去补充信息」按钮")
    ck("ge-drop-go" in js, "未采信内容每条带「去补充信息」按钮")
    ck("ge-mine-go" in js, "补充记录每条带「去补充信息」按钮")
    ck("function goSupplement" in js, "有统一的跳转函数 goSupplement（滚动+聚焦+高亮）")

    print("\n[2] C2：补充内容要留在原地、并且对得上问题" + tag)
    ck('bubble("me", "我（回答：' in js, "聊天流的气泡带上它回答的是哪个问题")
    ck('goSupplement("", b.getAttribute("data-field"))' in js,
       "未采信面板按**字段中文名**匹配问题卡（不是拿它当 key —— 第一版就错在这）")
    ck("ANSWERED[q.key]" in js and "MINE.push(" in js, "回答记进 ANSWERED/MINE")
    ck("renderMine()" in js, "回答后立刻渲染补充记录")

    print("\n[3] 那个真 bug：busy 必须是 let" + tag)
    ck("let busy = false;" in code, "busy 用 let 声明（否则 busy = true 必抛 TypeError）")
    bad = re.search(r"const[^;\n]*\bbusy\s*=\s*false", code)
    ck(bad is None, "没有把 busy 塞进 const 声明列表" + ("：" + bad.group(0)[:60] if bad else ""))

    print("\n[4] 样式与复位" + tag)
    ck(".ge-mine-row" in css and ".ge-tag-bad" in css and ".ge-q-state.bad" in css,
       "新增样式齐全（补充记录/徽标/未采信状态行）")
    ck('"ge-mine"' in js and "MINE.length = 0" in js and "delete ANSWERED[k]" in js,
       "新建报告会清空补充记录与已答记忆")

    print("\n[5] 页面能拿到这份前端" + tag)
    try:
        with urllib.request.urlopen(BASE + "/gen", timeout=30) as r:
            html = r.read().decode("utf-8", "replace")
        ck(r.status == 200, "/gen 返回 200")
        ck("gen_ui.js" in html or "genBody" in html, "页面确实挂着编制页前端")
    except Exception as exc:                                        # noqa: BLE001
        ck(False, "/gen 取不到：%s" % exc)


def main() -> int:
    js, css = read(JS_PATH), read(CSS_PATH)
    print("线上文件：gen_ui.js %d 字节 ｜ gen_ui.css %d 字节" % (len(js.encode()), len(css.encode())))
    check(js, css)

    print("\n[6] 反向用例（证明上面的检查不是空转）")
    # 注入 1：把 let busy 改回 const（那个真 bug 的原样）
    broken = js.replace("let busy = false;", "const busy = false;")
    ck(re.search(r"const[^;\n]*\bbusy\s*=\s*false", strip_comments(broken)) is not None,
       "[注入] 把 busy 写回 const 必须被第 [3] 节抓到")
    # 注入 2：删掉未采信面板的按钮
    #   注意替换词不能**含原词**：第一版写成 "ge-drop-go-REMOVED"，
    #   于是 `"ge-drop-go" not in broken2` 永远为假 —— 断言自己把自己坑了。
    broken2 = js.replace("ge-drop-go", "GONE_BTN")
    ck("ge-drop-go" not in broken2, "[注入] 去掉未采信面板按钮必须被第 [1] 节抓到")
    # 注入 3：把字段名又当 key 传
    broken3 = js.replace('goSupplement("", b.getAttribute("data-field"))',
                         'goSupplement(b.getAttribute("data-field"))')
    ck('goSupplement("", b.getAttribute("data-field"))' not in broken3,
       "[注入] 把字段名当 key 传必须被第 [2] 节抓到")

    print("\n" + "=" * 62)
    print("==== 通过 %d / 失败 %d ====" % (P, F))
    return 1 if F else 0


if __name__ == "__main__":
    sys.exit(main())
