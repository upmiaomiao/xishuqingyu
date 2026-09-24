#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核界面（可挂载模块 + 两个宿主页面）的静态一致性校验。

为什么需要：界面代码里 id/类名写错，只有人点开浏览器才会发现（而且不一定点得到那一步）。
这里在**部署前**把三类低级错误抓出来：
  ① JS 语法错误（调 node --check）；
  ② JS 引用了某个 id，但生成的 HTML 里没有这个 id（拼错/改名没跟上）；
  ③ 用了某个 au- 类名，但 CSS 里没定义（漏样式，界面会"看着不对"却说不出哪里不对）。

★ 2026-09-19 更新（原来是按重构前的结构写的，跑起来直接崩）：
  09-18 阶段 3 把界面改成了 **ES 模块**——
    · `frontend/index.html` 不再有内联 `<script>`，只剩 `<script type="module" src="/static/js/main.js">`；
      审核模块的按需加载搬进了 `frontend/js/views.js`（`ensureAuditUI` → `import('/audit/static/audit_ui.js')`）；
    · 独立页外壳 `audit.html` 只加载 `audit_page.js`（它再 import `audit_ui.js`），
      `?embed=1` 由 `audit_page.js` 加 `body.au-embed`、`audit_page.css` 里 `body.au-embed header{display:none}`。
  旧版直接 `re.search(r"<script>(.*)</script>", host)` 抓内联脚本 —— 抓不到成 None，脚本当场
  AttributeError 崩掉（**测试崩了比测试失败更糟：它连"哪里不对"都说不出来**）。
  现在改为按模块结构断言，并把"部署源里必须有 audit_page.js/.css"也纳入检查。

用法：python 单测_审核界面.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # 本文件目录（单测/）
BASE = os.path.dirname(HERE)                               # 审核智能体/
SRV = os.path.join(BASE, "服务端")
UI = os.path.join(SRV, "static", "audit_ui.js")
CSS = os.path.join(SRV, "static", "audit_ui.css")
# 2026-09-22 新增：原文批注视图独立成模块（audit_ui.js 已 600 行，再塞进去
# 会变成第二个"什么都在里面"的文件）。新模块同样纳入这四类检查 ——
# 否则新代码就是"没人管的那一半"。
DOC = os.path.join(SRV, "static", "audit_doc.js")
PAGE_JS = os.path.join(SRV, "static", "audit_page.js")     # 独立页外壳模块
PAGE_CSS = os.path.join(SRV, "static", "audit_page.css")
SHELL = os.path.join(SRV, "audit.html")
# 宿主页面的两份副本（权威副本优先，镜像兜底）——两份都该与线上一致
_FRONT_CANDS = [os.path.join(BASE, "..", "..", "_中间产物", "重构工作区", "frontend"),
                os.path.join(BASE, "..", "..", "服务器会话", "xishu_site", "frontend")]
FRONT = next((p for p in _FRONT_CANDS if os.path.isdir(p)), _FRONT_CANDS[0])
HOST = os.path.join(FRONT, "index.html")
HOST_JS = os.path.join(FRONT, "js", "views.js")            # 按需加载在这里

OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print(f"  √ {name}")
    else:
        FAIL += 1
        print(f"  × {name} {extra}")


def node_check(path):
    try:
        r = subprocess.run(["node", "--check", path], capture_output=True, text=True, timeout=60)
        return r.returncode == 0, (r.stderr or "").strip()[:300]
    except FileNotFoundError:
        return None, "未安装 node，跳过语法检查"


def main():
    ui = open(UI, encoding="utf-8").read()
    css = open(CSS, encoding="utf-8").read()
    doc = open(DOC, encoding="utf-8").read() if os.path.isfile(DOC) else ""
    shell = open(SHELL, encoding="utf-8").read()
    host = open(HOST, encoding="utf-8").read()
    host_js = open(HOST_JS, encoding="utf-8").read() if os.path.isfile(HOST_JS) else ""

    print("[1] JS 语法与模块化结构")
    ok, err = node_check(UI)
    check("audit_ui.js 语法", ok is not False, err)
    # 新模块必须真的在部署源里（2026-09-22 踩过：新文件只放进了站点镜像树，
    # 部署源里没有 —— 从部署源发一次版就把刚上线的功能整个盖掉，且不报错）
    check("部署源里有 audit_doc.js（原文批注视图模块）", os.path.isfile(DOC), f"缺 {DOC}")
    if os.path.isfile(DOC):
        ok, err = node_check(DOC)
        check("audit_doc.js 语法", ok is not False, err)
    check("audit_ui.js 以模块方式引入批注视图", "from './audit_doc.js'" in ui)
    # 外壳模块必须存在（2026-09-19 发现：线上有、部署源里没有 —— 照部署源发版会把独立页发坏）
    check("部署源里有 audit_page.js（独立页外壳模块）", os.path.isfile(PAGE_JS), f"缺 {PAGE_JS}")
    check("部署源里有 audit_page.css（外壳样式）", os.path.isfile(PAGE_CSS), f"缺 {PAGE_CSS}")
    if os.path.isfile(PAGE_JS):
        ok, err = node_check(PAGE_JS)
        check("audit_page.js 语法", ok is not False, err)
    inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", host, re.I)
    check("首页无内联脚本（重构后只剩模块入口）", not inline, f"仍有 {len(inline)} 段内联")
    check("首页以模块方式加载 /static/js/main.js",
          'type="module"' in host and "/static/js/main.js" in host)

    print("[2] id 引用是否都有定义")
    refs = set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", ui))
    refs |= set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", ui))
    refs |= set(re.findall(r"querySelector\('#([A-Za-z0-9_-]+)'\)", ui))
    # 批注视图模块的 id 由它自己拼的 HTML 提供（dom.wrap.querySelector('#auToc') 这种）
    refs |= set(re.findall(r"querySelector\('#([A-Za-z0-9_-]+)'\)", doc))
    refs |= set(re.findall(r"getElementById\('([A-Za-z0-9_-]+)'\)", doc))
    refs |= set(re.findall(r"\$\('#([A-Za-z0-9_-]+)'\)", doc))
    ids_ui = set(re.findall(r'id="([A-Za-z0-9_-]+)"', ui))
    ids_ui |= set(re.findall(r'id="([A-Za-z0-9_-]+)"', doc))
    ids_shell = set(re.findall(r'id="([A-Za-z0-9_-]+)"', shell))
    ids_host = set(re.findall(r'id="([A-Za-z0-9_-]+)"', host))
    missing = sorted(refs - ids_ui - ids_shell - ids_host)
    check(f"JS 引用的 {len(refs)} 个 id 全部有定义", not missing, f"缺：{missing}")

    print("[3] 宿主页面接线（按需加载已移入 js/views.js）")
    check("首页有挂载容器 #auditBody", 'id="auditBody"' in host)
    check("views.js 里有按需加载函数 ensureAuditUI", "ensureAuditUI" in host_js)
    check("views.js 动态 import 审核模块", "import('/audit/static/audit_ui.js')" in host_js)
    check("views.js 把模块挂到 #auditBody",
          "mountAuditUI(document.getElementById('auditBody'))" in host_js)
    check("审核入口是原生挂载（不用 auditFrame）", "auditFrame" not in host)
    check("首页 iframe 只用于原文预览",
          host.count("<iframe") == 1 and 'id="docFrame"' in host, f"iframe {host.count('<iframe')} 个")
    check("首页不再借用知识图谱样式给审核", 'class="kg-view" id="auditView"' not in host)
    check("首页给审核/编制各自独立视图容器",
          'id="auditView"' in host and 'id="genView"' in host)
    check("独立页加载外壳模块 audit_page.js", "/audit/static/audit_page.js" in shell)
    check("外壳模块 import 同一份 audit_ui.js", "from './audit_ui.js'" in open(PAGE_JS, encoding="utf-8").read()
          if os.path.isfile(PAGE_JS) else False)
    check("独立页支持 ?embed=1 隐藏自身页头",
          "embed=1" in open(PAGE_JS, encoding="utf-8").read()
          and "au-embed" in open(PAGE_CSS, encoding="utf-8").read()
          if os.path.isfile(PAGE_JS) and os.path.isfile(PAGE_CSS) else False)
    check("独立页返回链接用 target=_top", 'target="_top"' in shell)
    check("模块只暴露一个 ES 导出入口",
          "export function mountAuditUI" in ui and "window.mountAuditUI" not in ui,
          f"export {'有' if 'export function mountAuditUI' in ui else '无'} / "
          f"window 挂载 {'有' if 'window.mountAuditUI' in ui else '无'}")

    print("[4] au- 类名是否都有样式")
    # 注意：CSS 变量写作 var(--au-danger)，不能当成类名来查（第一版检查脚本就栽在这里）
    # 外壳类（.au-page-root / header .au-sub）定义在 audit_page.css，组件类在有 audit_ui.css —— 两份都要算。
    css_all = css + (open(PAGE_CSS, encoding="utf-8").read() if os.path.isfile(PAGE_CSS) else "")
    used = set(re.findall(r"(?<!-)au-[a-z0-9-]+", ui)) | set(re.findall(r"(?<!-)au-[a-z0-9-]+", shell))
    used |= set(re.findall(r"(?<!-)au-[a-z0-9-]+", doc))
    defined = set(re.findall(r"\.(au-[a-z0-9-]+)", css_all))
    used |= set(re.findall(r"'(au-[a-z0-9-]+)'", ui))
    used |= set(re.findall(r"'(au-[a-z0-9-]+)'", doc))
    used = {u for u in used if not u.startswith("au-shell") or True}
    undef = sorted(u for u in used - defined if not u.endswith("-"))
    check(f"用到的 au- 类名都有样式（{len(used)} 个）", not undef, f"缺样式：{undef}")

    # 动态拼出来的类名（`'au-note-' + SEV_CLS[结论]`）静态扫不到 —— 扫不到就等于没检查，
    # 拼错一个取值，界面上只是"颜色不对"，不报错、不空白，最难发现。这里按取值表逐个数。
    for var, pref in (("SEV_CLS", "au-note-"), ("LVL_CLS", "au-hl-"), ("LVL_CLS", "au-lvl-")):
        block = re.search(var + r"\s*=\s*\{(.*?)\};", doc, re.S)
        vals = sorted(set(re.findall(r":\s*'([a-z]+)'", block.group(1)))) if block else []
        miss = [v for v in vals if pref + v not in defined]
        check(f"{var} 的 {len(vals)} 个取值都有 {pref}* 样式", not miss, f"缺：{miss}")

    print("[4b] 通用规则不得盖掉组件（CSS 层叠顺序）")
    # 背景：实测踩过 —— `.au-shell button`（specificity 0-1-1，蓝底 + height:32px）
    # 把统计卡 `.au-card`（0-1-0，白底 + height:auto）盖掉，卡片变蓝、标签被切（用户截图发现）。
    # 关键：组件"声明了"这两项也没用，**specificity 输了就输**。所以这里真算 specificity。
    rules = []
    # 先去掉 CSS 注释：否则 `/* … */ .au-shell .au-card` 这种会把注释算进选择器，
    # 导致匹配失败、检查形同虚设（第一版检查就栽在这里）。
    css_clean = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", css_clean, re.S):
        sels, body = m.group(1), m.group(2)
        if sels.strip().startswith("@") or "{" in sels:
            continue
        props = set(re.findall(r"([a-z-]+)\s*:", body))
        for one in sels.split(","):
            one = " ".join(one.split())
            if one and not one.startswith("@"):
                rules.append((one, props))

    def spec(sel):
        """粗略 specificity：(id 数, 类/属性/伪类数, 元素数)。够用来比较这里的规则。"""
        ids = len(re.findall(r"#[\w-]+", sel))
        cls = len(re.findall(r"[.\[][\w-]+", sel)) + len(re.findall(r":(?!:)[\w-]+", sel))
        el = len(re.findall(r"(?:^|[\s>+~])([a-z][\w-]*)", sel))
        return (ids, cls, el)

    # 组件类 → 元素类型（从 JS 里 `el('button','au-x')` 与 `<button class="au-x…">` 取）
    pairs = set()
    for tag, attr in (re.findall(r"<(\w+)[^>]*class=\"([^\"]*au-[a-z0-9-]+)", ui)
                      + re.findall(r"el\('(\w+)',\s*'([^']*au-[a-z0-9-]+)", ui)):
        for c in attr.split():
            if c.startswith("au-"):
                pairs.add((tag.lower(), c))
    problems = []
    for tag, cls in sorted(pairs):
        # 只比**同类元素**的宽规则（`.au-x select` 管不到 <button>），
        # 且只比**默认态**规则：`.au-card:hover` / `.au-card.on` 带条件，
        # 挡不住默认态被盖（旧 CSS 里 `.au-shell .au-card:hover{background:white}`
        # 曾让检查误判为"已保护"）。
        broad = [(s, p, spec(s)) for s, p in rules
                 if re.fullmatch(r"\.au-[\w-]+ +%s" % tag, s)]
        base = re.compile(r"(?:\.au-[\w-]+ +)*\.%s$" % re.escape(cls))
        own = [(s, p, spec(s)) for s, p in rules if base.fullmatch(s)]
        for s, p, sp in broad:
            for prop in ("background", "height", "padding", "border", "color"):
                if prop not in p:
                    continue
                mine = [o[2] for o in own if prop in o[1]]
                # 只有"组件**自己声明了**这个属性、却因 specificity 不够而输给宽规则"才算问题。
                # 组件压根没声明（例如 `.au-new` 不管 color、`.au-pick` 不管 height）时，
                # 由宽规则统一给值正是设计意图，不算冲突。
                if not mine:
                    continue
                best = max(mine)
                if best <= sp:
                    problems.append(f"{cls} 的 {prop} 被 `{s}`（{sp[1]}类{sp[2]}元素）盖掉："
                                    f"默认态组件自身最高仅 {best[1]}类{best[2]}元素")
    check(f"带 au- 类的组件（{len(pairs)} 个）不被宽规则覆盖", not problems, "；".join(problems))

    print("[5] 接口路径与后端一致")
    py = open(os.path.join(SRV, "audit_routes.py"), encoding="utf-8").read()
    # 后端路由挂在 /audit 前缀下，路径形如 /api/reports
    for ep in ("/api/reports", "/api/run", "/api/job/", "/api/review/", "/api/save",
               "/api/export/", "/api/download/", "/api/pdf/", "/static/",
               # 2026-09-22 原文批注视图
               "/api/annot/", "/api/page/", "/api/pageimg/"):
        check(f"后端提供 {ep}", f'"{ep}' in py, "路由里没找到")
    for call in sorted(set(re.findall(r"API \+ '(/[a-z/]*)'", ui + doc))):
        check(f"前端调用 /api{call} 有后端对应", f'"/api{call}' in py, "")

    print(f"\n==== 通过 {OK} / 失败 {FAIL} ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())