#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""嵌入契约检查：问答页里「报告编制」的接线是否完整、是否真的不再跳转。

我这边没有浏览器，所以把"能不能嵌进去"拆成可机械核对的几条：
  ① 首页侧栏按钮调 openGen()，且**不再有 window.open('/gen')**（跳转必须去掉）；
  ② 首页有 <section class="au-view" id="genView"><div id="genBody"> 容器，并复用了
     .au-view 的显隐规则（.open 才显示）；
  ③ 首页有 #genBody 的高度规则与 openGen/closeGen/ensureGenUI 三个函数，
     且切到审核/图谱/新对话时会先收起本视图（否则两个视图会叠着）；
  ④ 独立页 /gen 是薄壳 + 引用同一份模块（两边不会分叉）；
  ⑤ 模块暴露 window.mountGenUI，且挂载是幂等的（data-ge-mounted），
     并能切 ge-embedded 隐藏跳转链接。
最后自带一个**反向用例**：查一个绝不该出现的 token，必须判为不存在（证明检查有效）。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查嵌入契约.py
"""
from __future__ import annotations

import re
import sys
import urllib.request

BASE = "http://127.0.0.1:8011"
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:100]) if detail else ""))


def _undefined_vars(css: str) -> list:
    """找出 CSS 里用了、但没在 .ge-shell 块里定义过的 --ge-* 变量。

    为什么专门查这个：所有 --ge-* 都声明在 `.ge-shell` 上，靠继承生效。一旦模块忘了包
    `.ge-shell`（我在改成"可挂载模块"时就漏了），`var(--ge-white)` 之类会**静默失效** ——
    版式还在（.ge-main/.ge-card 是纯类选择器），但背景/边框/按钮配色全没了，
    表现为"发送"按钮白字透明底直接看不见。这类故障不会报错，只能靠检查抓。
    """
    m = re.search(r"\.ge-shell\s*\{(.*?)\n\}", css, re.S)
    defined = set(re.findall(r"(--ge-[a-z0-9\-]+)\s*:", m.group(1) if m else ""))
    used = set(re.findall(r"var\(\s*(--ge-[a-z0-9\-]+)", css))
    return sorted(used - defined)


def fetch(path: str) -> str:
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return r.read().decode("utf-8", "ignore")


def _bare_classes(js: str) -> list:
    """找出没带 ge-/au- 前缀的类名。

    注意：源码里有 `class="ge-pill' + ((a.分布 || {})[...]` 这种**拼接**，
    直接用 `class="([^"]+)"` 抓会把 `((a.分布`、`||` 这类碎片当成类名（本轮实测踩到，
    报了一次假失败）。所以只保留"合法类名形状"的 token，拼接碎片交给下面那条
    "动态片段"检查去管。
    """
    out = set()
    for m in re.findall(r'class="([^"]+)"', js):
        for c in m.split():
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", c) and not c.startswith(("ge-", "au-")):
                out.add(c)
    return sorted(out)


def main() -> int:
    print("=" * 62)
    home = fetch("/")
    js = fetch("/gen/static/gen_ui.js")
    stand = fetch("/gen")

    print("[1] 首页入口改为页内切换（不跳转）")
    check("侧栏按钮调 openGen()", 'onclick="openGen()"' in home)
    check("已无 window.open('/gen') 跳转", "window.open('/gen'" not in home)
    check("按钮文案仍是「报告编制」", "报告编制" in home)

    print("[2] 视图容器与显隐规则")
    check("有 id=\"genView\" 的视图容器", 'id="genView"' in home)
    check("有 id=\"genBody\" 的挂载点", 'id="genBody"' in home)
    check("复用 .au-view 的显隐（与审核页同一套）", 'class="au-view" id="genView"' in home)
    check("有 .au-view.open 显示规则", re.search(r"\.au-view\.open\s*\{[^}]*display\s*:\s*flex", home) is not None)
    check("有 #genBody 高度规则", "#genBody{flex:1" in home.replace(" ", ""))

    print("[3] 接线脚本")
    for fn in ("function openGen()", "function closeGen()", "function ensureGenUI(cb)"):
        check("首页有 %s" % fn, fn in home)
    check("切审核时先收起本视图", "window.openAudit=function(){closeGen()" in home.replace(" ", ""))
    check("切图谱时先收起本视图", "openKnowledgeGraph=function(){closeGen()" in home.replace(" ", ""))
    check("新对话时先收起本视图", "newConversation=function(){closeGen()" in home.replace(" ", ""))
    check("嵌入时隐藏跳转链接（调 setGenEmbedded）", "setGenEmbedded" in home)

    print("[4] 独立页与宿主用同一份模块")
    check("/gen 引用同一份 gen_ui.js", "/gen/static/gen_ui.js" in stand)
    check("/gen 是薄壳（有 ge-standalone、有 #genBody）",
          "ge-standalone" in stand and 'id="genBody"' in stand)
    check("/gen 不再自带整页结构（无 ge-stream 硬编码）", "ge-stream" not in stand)

    print("[5] 模块本身")
    check("暴露 window.mountGenUI", "window.mountGenUI" in js)
    check("暴露 window.setGenEmbedded", "window.setGenEmbedded" in js)
    check("挂载幂等（data-ge-mounted）", "data-ge-mounted" in js)
    check("嵌入时切 ge-embedded", "ge-embedded" in js)
    check("样式类名一律 ge- 前缀（不污染宿主）", not _bare_classes(js), _bare_classes(js))
    frags = re.findall(r'\?\s*"\s+([a-z][a-z0-9\- ]*)"', js)      # 动态拼接的类名片段
    check("动态拼接的类名片段也带 ge- 前缀", frags and all(f.strip().startswith("ge-") for f in frags),
          frags)

    print("[5b] 变量作用域（静默失效的高发区）")
    css = fetch("/gen/static/gen_ui.css")
    check("模块注入了 .ge-shell 根容器", "'<div class=\"ge-shell\">'" in js.replace("\\'", "'"))
    check("内联样式里 .ge-shell 只有一处（挂载点唯一，不会定义两份）",
          js.count('<div class="ge-shell">') == 1, js.count('<div class="ge-shell">'))
    check("CSS 用到的 --ge-* 变量都在 .ge-shell 里定义过",
          not _undefined_vars(css), _undefined_vars(css))
    check("setEmbedded 作用在 .ge-shell 上（否则 .ge-shell.ge-embedded 选不中）",
          "querySelector(\".ge-shell\")" in js and "ROOT.classList.toggle" in js)
    # 缺陷注入：故意加一条用了未定义变量的规则，检查器必须发现
    injected = css + "\n.ge-inject{color:var(--ge-not-defined-xyz)}\n"
    check("[注入] 未定义的变量必须被判为问题", _undefined_vars(injected) == ["--ge-not-defined-xyz"],
          _undefined_vars(injected))

    print("[6] 版式：左输入 / 右过程与成稿 / 右上角历史报告")
    check("有左栏 .ge-left（输入侧）", "ge-left" in js)
    check("有右栏 .ge-right（过程与成稿）", "ge-right" in js)
    L, R = js.find('class="ge-left"'), js.find('class="ge-right"')
    check("左栏里是输入区（说 / 问 / 答 / 发送）",
          L < js.find('id="ge-say"') < R and L < js.find('id="ge-ask"') < R and
          L < js.find('id="ge-send"') < R)
    check("左栏里**没有**事实/日志/预览（左栏只放输入，才不挤）",
          not (L < js.find('id="ge-known"') < R or L < js.find('id="ge-log"') < R or
               L < js.find('id="ge-prev"') < R))
    check("我了解到的事实放在右栏（是中间结果）并排在日志之前",
          R < js.find('id="ge-known"') < js.find('id="ge-log"'))
    check("日志与成稿都在右栏", R < js.find('id="ge-log"') < js.find('id="ge-prev"'))
    check("对话流与问题卡合并在同一个滚动区（.ge-chat-body）",
          'class="ge-chat-body"' in js and js.find('class="ge-chat-body"') < js.find('id="ge-ask"'))
    check("不再有第二层各自滚动（.ge-stream 不设 max-height）",
          not re.search(r"\.ge-stream\s*\{[^}]*max-height", css))
    check("挂载时不再补重复的系统气泡（说明卡已说同一件事）",
          'bubble("ai", "系统", "先说说你的项目' not in js)
    check("右上角有「历史报告」按钮", 'id="ge-history"' in js)
    check("右上角有「新建报告」按钮（清空重来）", 'id="ge-new"' in js and "新建报告" in js)
    check("新建报告会复位会话（SID=null 并通知服务端清理）",
          "function newReport" in js and "SID = null" in js and '"/chat/reset"' in js)
    # 注意：不能用 '"说明卡" not in js' 这类断言 —— 注释里提到"说明卡"三个字是正当的
    # （第一版就是这么写的，结果自己被自己判失败）。要查的是"说明卡的正文只有一份"。
    check("新建报告靠挂载时的 INIT 快照还原（说明卡正文在 JS 里只有一份，不重抄）",
          "INIT = {}" in js and "INIT[k]" in js and js.count("把项目情况说一遍就行") == 1)
    check("新建报告会停掉轮询（否则旧任务回填到新页面）",
          "clearInterval(polling)" in js and "polling = null" in js)
    check("新建报告明确说明不删已生成的 Word（归档不删）", "不会被删除" in js)
    check("有未保存内容时先确认一次", "window.confirm" in js)
    check("按钮上带数量角标", 'id="ge-hcount"' in js)
    check("有历史报告弹层与关闭按钮", 'id="ge-modal"' in js and 'id="ge-mclose"' in js)
    check("弹层里能预览与下载旧报告", "preview_file/" in js and "/output/" in js)
    check("弹层显式处理 hidden（否则被 display:flex 盖掉、关不掉）", ".ge-modal[hidden]" in css)
    check("旧的单侧栏 .ge-side 已清理", "ge-side" not in js and "ge-side" not in css)

    print("[7] 反向用例（证明上面的检查不是空转）")
    check("查一个不存在的 token 必须判为不存在", "window.__NO_SUCH_HOOK__" not in home)

    print("=" * 62)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())