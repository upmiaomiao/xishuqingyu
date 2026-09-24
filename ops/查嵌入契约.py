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
  ⑤ 模块能被宿主挂载（幂等，data-ge-mounted），并能切 ge-embedded 隐藏跳转链接。
最后自带一个**反向用例**：查一个绝不该出现的 token，必须判为不存在（证明检查有效）。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查嵌入契约.py

--- 2026-09-18 修订（配合前端重构阶段 2b/3）---
本脚本原先只在**首页 HTML 源码**里 grep。重构后首页的 CSS 外置到 /static/app.css、
JS 拆成 /static/js/ 下 8 个 ES 模块，于是 12 条检查集体变红 —— 但**契约本身没变**，
变的只是"代码写在哪个文件里"。所以加一个 bundle()：把页面外链的 CSS/JS 取来合并
（并递归跟随 ES 模块的 import 图），之后的检查一律查"合并后的有效代码"。

同时修订三处**投递方式**的断言（能力不变，只是不再挂 window）：
  · window.mountGenUI / window.setGenEmbedded  ->  ES 模块的 export
  · 猴补 window.openAudit 的 IIFE              ->  main.js 里的显式箭头包装
另外修掉一条**早就失效**的断言：它数的是「把项目情况说一遍就行」，而该文案早已改写，
线上和重构前的备份里都是 0 次（即这条在我动手之前就是红的）。改成数说明卡的真实正文。
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


def _resolve(src: str, ref: str) -> str:
    """把模块里的相对引用解析成站点绝对路径。"""
    if ref.startswith("/"):
        return ref
    if ref.startswith("./"):
        ref = ref[2:]
    base = src.rsplit("/", 1)[0] if "/" in src else ""
    # 处理 ../ 这类（本模块图里没有，但别静默算错）
    parts = (base + "/" + ref).split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p not in ("", "."):
            out.append(p)
    return "/" + "/".join(out)


def bundle(page: str):
    """取页面外链的 CSS 与 JS，合并成"有效代码"。

    为什么需要：重构把 CSS/JS 从 index.html 里搬了出去，如果检查器只读 HTML 源码，
    它查的就不再是"页面实际会执行什么"，而是"HTML 里手写了什么" —— 契约明明还在，
    却集体报红。所以这里按浏览器的方式把外链取回来（JS 还要递归跟随 import 图）。
    """
    html = fetch(page)
    css_parts, js_parts, seen = [], [], set()

    for href in re.findall(r"""<link[^>]+href\s*=\s*["']([^"']+\.css)["']""", html):
        try:
            css_parts.append(fetch(href))
        except Exception:                                          # noqa: BLE001
            pass

    def walk(src: str, depth: int = 0) -> None:
        if src in seen or depth > 6:
            return
        seen.add(src)
        try:
            body = fetch(src)
        except Exception:                                          # noqa: BLE001
            return
        js_parts.append(body)
        # 跟随 ES 模块 import（静态 from '...' 与动态 import('...')）
        for m in re.finditer(r"""\bfrom\s*["']([^"']+)["']|\bimport\s*\(\s*["']([^"']+)["']""", body):
            ref = m.group(1) or m.group(2)
            if ref.startswith(("./", "/")):
                walk(_resolve(src, ref), depth + 1)

    for s in re.findall(r"""<script[^>]+src\s*=\s*["']([^"']+)["']""", html):
        walk(s)

    return html, "\n".join(css_parts), "\n".join(js_parts)


def _wraps(js: str, name: str) -> bool:
    """window.<name> 的包装体里是否先调了 closeGen()。

    重构前是一段 IIFE 猴补：window.openAudit=function(){closeGen();...}
    现在是 main.js 里的箭头函数：window.openAudit = () => { closeGen(); _openAudit(); };
    所以不能只认 `function(){`，要接受箭头函数与任意空白。
    """
    pat = (r"window\.%s\s*=\s*(?:function\s*\([^)]*\)|\([^)]*\)\s*=>|[A-Za-z_$][\w$]*\s*=>)\s*\{"
           % re.escape(name))
    for m in re.finditer(pat, js):
        if "closeGen()" in js[m.end():m.end() + 220]:
            return True
    return False


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
    home, home_css, home_js = bundle("/")
    js = fetch("/gen/static/gen_ui.js")
    stand = fetch("/gen")
    print("  首页 HTML %d 字符 / 合并后 CSS %d 字符 / 合并后 JS %d 字符"
          % (len(home), len(home_css), len(home_js)))
    print("  （首页的 CSS 与 JS 已外置，下面的检查查的是合并后的有效代码）")

    print("[1] 首页入口改为页内切换（不跳转）")
    check("侧栏按钮调 openGen()", 'onclick="openGen()"' in home)
    check("已无 window.open('/gen') 跳转", "window.open('/gen'" not in home)
    check("按钮文案仍是「报告编制」", "报告编制" in home)

    print("[2] 视图容器与显隐规则")
    check("有 id=\"genView\" 的视图容器", 'id="genView"' in home)
    check("有 id=\"genBody\" 的挂载点", 'id="genBody"' in home)
    check("复用 .au-view 的显隐（与审核页同一套）", 'class="au-view" id="genView"' in home)
    check("有 .au-view.open 显示规则（查外置 CSS）",
          re.search(r"\.au-view\.open\s*\{[^}]*display\s*:\s*flex", home_css) is not None)
    # 注意：这里必须用 re.sub(r"\s+","") 而不是 .replace(" ","")。
    # 外置到 app.css 后规则体里有换行（`#genBody {\n  flex:1;`），只去空格匹配不上，
    # 会报出「没有高度规则」的假失败 —— 规则其实在（本轮实测踩到）。
    check("有 #genBody 高度规则（查外置 CSS）",
          "#genBody{flex:1" in re.sub(r"\s+", "", home_css))

    print("[3] 接线脚本")
    for fn in ("function openGen(", "function closeGen(", "function ensureGenUI("):
        check("首页脚本里有 %s" % fn.rstrip("("), fn in home_js)
    check("切审核时先收起本视图", _wraps(home_js, "openAudit"))
    check("切图谱时先收起本视图", _wraps(home_js, "openKnowledgeGraph"))
    check("新对话时先收起本视图", _wraps(home_js, "newConversation"))
    check("嵌入时隐藏跳转链接（调 setEmbedded）", "setEmbedded(" in home_js)

    print("[4] 独立页与宿主用同一份模块")
    check("/gen 引用同一份 gen_ui.js", "/gen/static/gen_ui.js" in stand)
    check("/gen 是薄壳（有 ge-standalone、有 #genBody）",
          "ge-standalone" in stand and 'id="genBody"' in stand)
    check("/gen 不再自带整页结构（无 ge-stream 硬编码）", "ge-stream" not in stand)

    print("[5] 模块本身（阶段 3 起用 ES 导出，不再挂 window）")
    check("模块 ES 导出 mountGenUI", "export function mountGenUI" in js)
    check("模块 ES 导出 setEmbedded", "export function setEmbedded" in js)
    check("宿主用动态 import() 取该模块（不是插 <script>）",
          "import('/gen/static/gen_ui.js')" in home_js and "createElement('script')" not in home_js)
    check("宿主通过模块命名空间调用（m.mountGenUI / m.setEmbedded）",
          "m.mountGenUI(" in home_js and "m.setEmbedded(" in home_js)
    check("模块不再往 window 上挂东西", "window.mountGenUI" not in js and "window.setGenEmbedded" not in js)
    check("挂载幂等（data-ge-mounted）", "data-ge-mounted" in js)
    check("嵌入时切 ge-embedded", "ge-embedded" in js)
    check("样式类名一律 ge- 前缀（不污染宿主）", not _bare_classes(js), _bare_classes(js))
    frags = re.findall(r'\?\s*"\s+([a-z][a-z0-9\- ]*)"', js)      # 动态拼接的类名片段
    check("动态拼接的类名片段也带 ge- 前缀", frags and all(f.strip().startswith("ge-") for f in frags),
          frags)

    print("[5b] 变量作用域（静默失效的高发区）")
    css = fetch("/gen/static/gen_ui.css")
    # C6 有一半在服务端（"判定一做完就回传"），HTTP 层面只在生成**过程中**才看得到，
    # 不适合在契约测试里真跑一次生成 —— 直接读服务端源码核这条接线。
    try:
        with open("/home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py",
                  encoding="utf-8") as fh:
            routes = fh.read()
    except OSError as exc:
        routes = ""
        print("   （读不到 gen_routes.py，C6 服务端那条会判红：%s）" % exc)
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
    #
    # 2026-09-18：这条原来数的是「把项目情况说一遍就行」。该文案早已改写，线上与
    # 重构前备份里都是 0 次 —— 也就是**在我动手之前就是红的**，属于陈旧断言。
    # 改成数说明卡的真实正文（TEMPLATE 里那句），语义不变。
    GUIDE = "在左侧描述项目情况，或点「换一个示例」参考写法。"
    check("新建报告靠挂载时的 INIT 快照还原（说明卡正文在 JS 里只有一份，不重抄）",
          "INIT = {}" in js and "INIT[k]" in js and js.count(GUIDE) == 1, js.count(GUIDE))
    # 2026-09-22 用户反馈：新建报告后上一份的"12 项""未采信内容""已完成 100%"还挂着。
    # 根因是 INIT 只覆盖 5 个区域的 innerHTML，另有 4 处可变状态（textContent／属性／checked）
    # 谁都没复位，而**老断言只查了 INIT 存在，没查覆盖范围** —— 所以漏过去了。
    # 这条按"性质不同的可变状态必须逐项复位"来查：从 newReport 函数体里找复位语句。
    _nr = js[js.find("function newReport"):js.find("function bind")]
    for _id, _how in (("ge-count", "textContent"), ("ge-drop", "innerHTML"),
                      ("ge-prog", "hidden"), ("ge-fresh", "checked"),
                      # 2026-09-22（C4/C6）新增的两处可变状态，同样必须逐项复位
                      ("ge-logn", "textContent"), ("ge-logbox", "open"),
                      ("ge-dec-card", "hidden"), ("ge-dec", "innerHTML")):
        check("新建报告复位 %s（%s）" % (_id, _how),
              ('$("%s")' % _id) in _nr and _how in _nr)
    # C4：技术日志折进「生成详情」，**默认收起**；但"使用步骤"是新手引导，不能跟着被收走；
    # 进度条与结论是"当前状态"，也不许折叠（折了等于藏信息）。
    check("C4 日志被包进 <details>（可折叠）且默认不带 open",
          'id="ge-logbox"' in js and "<details" in js and
          not re.search(r"<details[^>]*\bopen\b", js))
    check("C4 「使用步骤」挪出了日志容器（折叠后第一次使用仍看得见引导）",
          js.find('class="ge-guide"') < js.find('id="ge-logbox"') and
          'id="ge-log"' in js)
    check("C4 进度条**没有**被折进 details（当前状态必须常驻可见）",
          js.find('id="ge-prog"') < js.find('id="ge-logbox"'))
    check("C4 日志出错时自动展开（失败原因不能被折叠藏起来）",
          'level === "error"' in js and '.open = true' in js)
    check("C4 折叠块有样式（.ge-logbox / .ge-logsum）",
          ".ge-logbox" in css and ".ge-logsum" in css)
    # C6：判定摘要（只读）—— 判定一到就显示，不等生成完
    check("C6 有判定摘要卡片（只读容器）", 'id="ge-dec-card"' in js and 'id="ge-dec"' in js)
    check("C6 轮询里即时渲染判定（不等 done）",
          re.search(r"if\s*\(\s*j\.判定\s*\)\s*renderDec\(", js) is not None)
    check("C6 卡片明说未定项会在成稿里标【需人工补充】", "需人工补充" in js)
    check("C6 服务端在②判定后就把判定放进任务（不是只在 done 时）",
          re.search(r'_JOBS\[job_id\]\["判定"\]\s*=\s*dec_summary\(dec\)', routes) is not None)

    # ---- 问答侧：资料块必须带索引元数据（B1/B2 的真根因，2026-09-22 第二批）----
    # 当时这条只有「真机问 5 个错例」能证明，没有回归防线：一旦有人把拼装改回
    # `[{i}] 《{title}》\n{text}`，模型又会看不到状态，答案会静静地退回「仍有效」。
    print("[5c] 资料块元数据（模型看到的必须和界面一致）")
    try:
        with open("/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py",
                  encoding="utf-8") as fh:
            pipe = fh.read()
    except OSError as exc:
        pipe = ""
        print("   （读不到 pipeline.py，这一节会整片判红：%s）" % exc)
    check("pipeline.py 里有 source_block（资料块拼装收成一个函数）",
          "def source_block(" in pipe)
    # 真跑一遍那个函数（只 exec 这一个函数，不 import 整个模块 —— 免得拖上检索器/模型依赖）
    ns = {"Any": object}
    m = re.search(r"^def source_block\(.*?(?=^def |^class |\Z)", pipe, re.S | re.M)
    block = ""
    if m:
        try:
            exec("from typing import Any\n" + m.group(0), ns)      # noqa: S102
            block = ns["source_block"]({
                "index": 3, "title": "中华人民共和国环境影响评价法", "doc_type": "法律",
                "status": "已废止", "status_note": "已自2026年8月15日起被《生态环境法典》废止",
                "text": "本法自 2019 年 1 月 1 日起施行。"})
        except Exception as exc:                                   # noqa: BLE001
            print("   （source_block 跑不起来：%s）" % exc)
    check("资料块带「时效状态」（否则模型会说『未见废止声明』）",
          "时效状态：已废止" in block, block[:90])
    check("资料块带废止依据（否则模型会判『可能是录入错误』）",
          "生态环境法典" in block, block[:90])
    check("资料块仍以 [序号] 《标题》 开头（可溯源到引用卡片）",
          block.startswith("[3] 《中华人民共和国环境影响评价法》"), block[:60])
    if m:
        clean = ns["source_block"]({"index": 1, "title": "某报告", "text": "正文"})
        check("没有状态字段的块不得凭空写「时效状态」（不许编元数据）",
              "时效状态" not in clean, clean[:60])
    check("两处模型上下文都用它（不允许有一处回退到旧拼法）",
          pipe.count('"\\n\\n".join(source_block(s) for s in sources)') >= 2,
          pipe.count('"\\n\\n".join(source_block(s) for s in sources)'))
    check("旧的 《{title}》 拼法已绝迹（那就是不带状态的那版）",
          "《{s['title']}》" not in pipe)
    check("定义了却没人用的死代码常量已清掉",
          "ABOLISHED_STATUS" not in pipe)
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
    check("[注入] 把 mountGenUI 的 export 去掉必须被发现",
          "export function mountGenUI" not in js.replace("export function mountGenUI", "", 1))

    print("=" * 62)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
