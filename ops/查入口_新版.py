#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查问答首页的"报告审核"入口与审核界面模块是否已正确上线。

为什么单独写脚本：远程命令里带引号和括号会被 PowerShell 吃掉（踩过多次），
把检查逻辑做成文件上传再跑最稳。

检查项：
  ① 首页内容与磁盘一致、控件计数正确、标签配平；
  ② 首页是**原生挂载**（有 #auditBody、按需加载模块、不用 auditFrame）；
  ③ 审核模块静态资源可取到，且 Content-Type 正确；
  ④ 独立页 /audit 仍是完整页面，?embed=1 可隐藏自身页头；
  ⑤ 静态路由**拒绝路径穿越**（这是新增路由，必须验证）。

★ 2026-09-19 更新（原来 3 项失败，全是"检查脚本没跟上 09-18 的重构"，不是功能坏了）：
  · 旧②"无 iframe"改为"不用 auditFrame" —— 首页现在有 `<iframe id="docFrame">` 用于**原文预览**，
    旧写法把正常的预览框也算成了"用 iframe 包审核"；
  · 旧②"按需加载模块"原来看 **index.html 的正文文本**，但按需加载已经搬到
    `js/views.js`（`ensureAuditUI` → `import('/audit/static/audit_ui.js')`）→ 现在改为**真的去取那个 js 来验**；
  · 旧④"embed 隐藏页头"原来看 `body.embed header`，重构后是 `audit_page.js` 给 body 加 `au-embed`、
    `audit_page.css` 里 `body.au-embed header{display:none}` → 改为验证这两个文件。
  教训：检查脚本自己也会过期；**过期后会一直报错，最后没人看**。所以这里断言的是"链路能走通"，
  而不是"某个字符串还在不在"。
"""
import hashlib
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8011"
LOCAL_INDEX = "/home/test/xishu_qingyu_serve/frontend/index.html"
OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  √ " + name)
    else:
        FAIL += 1
        print("  × " + name + " " + extra)


def get(path, raw=False):
    """取一个 URL；响应头统一转小写 —— uvicorn 发的是小写 content-type，
    按大写取会取不到（这个坑踩过一次）。"""
    try:
        r = urllib.request.urlopen(BASE + path, timeout=40)
        body = r.read()
        hd = {k.lower(): v for k, v in r.headers.items()}
        return r.status, hd, (body if raw else body.decode("utf-8", "replace"))
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in e.headers.items()}, ""


def main():
    print("[1] 问答首页")
    st, hd, html = get("/")
    disk = open(LOCAL_INDEX, encoding="utf-8").read()
    check("状态 200", st == 200, str(st))
    check("线上内容与磁盘文件一致",
          hashlib.md5(html.encode()).hexdigest() == hashlib.md5(disk.encode()).hexdigest())
    for pat, want in {'class="composer-wrap"': 1, 'id="auditView"': 1, 'id="auditBody"': 1,
                      'onclick="openAudit()"': 1, 'onclick="openKnowledgeGraph()"': 1,
                      'onclick="newConversation()"': 1}.items():
        got = html.count(pat)
        check(pat + " = " + str(want), got == want, "实际 " + str(got))
    check("审核入口是原生挂载（不用 auditFrame）", "auditFrame" not in html)
    check("首页 iframe 只用于原文预览",
          html.count("<iframe") == 1 and 'id="docFrame"' in html,
          "iframe " + str(html.count("<iframe")) + " 个")
    # 按需加载搬进了 js/views.js —— 直接取那个 js 来验，而不是在 HTML 文本里找关键字
    st, hd, vjs = get("/static/js/views.js")
    check("views.js 可取到", st == 200, str(st))
    check("按需加载审核模块", "ensureAuditUI" in vjs and "import('/audit/static/audit_ui.js')" in vjs)
    check("挂到 #auditBody", "mountAuditUI(document.getElementById('auditBody'))" in vjs)
    check("标签配平 section", html.count("<section") == html.count("</section>"))
    check("标签配平 main/aside", html.count("<main") == html.count("</main>")
          and html.count("<aside") == html.count("</aside>"))

    print("[2] 审核界面静态资源")
    st, hd, js = get("/audit/static/audit_ui.js")
    check("audit_ui.js 200", st == 200, str(st))
    check("js Content-Type 为 javascript", "javascript" in hd.get("content-type", ""),
          hd.get("content-type", "（无）"))
    check("js 含挂载入口", "mountAuditUI" in js)
    st, hd, css = get("/audit/static/audit_ui.css")
    check("audit_ui.css 200", st == 200, str(st))
    check("css Content-Type 为 css", "css" in hd.get("content-type", ""),
          hd.get("content-type", "（无）"))
    check("css 含站点主色回退", "--au-primary: var(--primary" in css)

    print("[3] 独立页 /audit")
    st, hd, page = get("/audit")
    check("200", st == 200, str(st))
    check("加载外壳模块 audit_page.js", "/audit/static/audit_page.js" in page)
    st, hd, pjs = get("/audit/static/audit_page.js")
    check("外壳模块可取到且 import 同一份 audit_ui.js",
          st == 200 and "from './audit_ui.js'" in pjs, str(st))
    check("?embed=1 由外壳模块加 body.au-embed", "embed=1" in pjs and "au-embed" in pjs)
    st, hd, pcss = get("/audit/static/audit_page.css")
    check("外壳样式里有 body.au-embed header{display:none}",
          st == 200 and "body.au-embed header" in pcss, str(st))
    st2, _, _ = get("/audit?embed=1")
    check("?embed=1 可访问", st2 == 200, str(st2))

    print("[4] 静态路由安全（不允许目录穿越）")
    for bad in ("/audit/static/../audit_routes.py", "/audit/static/audit_routes.py",
                "/audit/static/..%2faudit_routes.py"):
        st, _, _ = get(bad)
        check("拒绝 " + bad, st in (400, 403, 404), "实际 " + str(st))

    print("[5] 其它")
    st, _, _ = get("/audit/api/reports")
    check("/audit/api/reports 200", st == 200, str(st))
    st, _, _ = get("/health")
    check("/health 200", st == 200, str(st))

    print("\n==== 通过 " + str(OK) + " / 失败 " + str(FAIL) + " ====")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())