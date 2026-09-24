#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""8011 站点全量 HTTP 实测（面向"这个网站到底能不能用、边界在哪"）。

与既有检查器的分工（不重复劳动）：
  · 既有套件查的是**引擎正确性**（判据/抽取/生成/契约）—— 已全绿；
  · 本脚本查**网页本身**：每个端点的正常路径 + 错误路径 + 安全边界 + 并发 + 耗时，
    以及"既有套件根本没碰过"的那一半（404/422/400 分支、目录穿越、XSS 转义、幂等）。

用法：
  python 全面测试_站点.py                 # 默认打 http://10.201.31.10:8011
  python 全面测试_站点.py --base http://127.0.0.1:8011
  python 全面测试_站点.py --skip-slow     # 跳过会真调模型的用例（RAG / 真实审核）

退出码 = 失败条数（0 = 全过）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"
OK, BAD, WARN, TIME = [], [], [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    mark = "√" if cond else "×"
    print("  %s %s%s" % (mark, name, ("　" + str(detail)[:150]) if detail else ""))


def note(name, detail=""):
    WARN.append(name)
    print("  ! %s%s" % (name, ("　" + str(detail)[:150]) if detail else ""))


def sec(t):
    print("\n" + "─" * 64)
    print(t)
    print("─" * 64)


def req(method, path, data=None, timeout=60, raw_body=None, headers=None):
    """返回 (status, headers, bytes, 秒)。不抛异常，把 HTTP 错误当数据。"""
    url = path if path.startswith("http") else BASE + path
    body = None
    h = dict(headers or {})
    if raw_body is not None:
        body = raw_body if isinstance(raw_body, bytes) else raw_body.encode("utf-8")
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, dict(resp.headers), resp.read(), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read(), round(time.time() - t0, 2)
    except Exception as e:                                    # noqa: BLE001
        return -1, {}, ("%s: %s" % (type(e).__name__, e)).encode("utf-8"), round(time.time() - t0, 2)


def J(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return None


def T(b):
    try:
        return b.decode("utf-8", "replace")
    except Exception:                                          # noqa: BLE001
        return ""


def timed(label, t):
    TIME.append((label, t))
    print("      · %s 用时 %.2fs" % (label, t))


def hget(hd, name, default=""):
    """大小写无关地取响应头。

    ★ 检查器自己踩过的坑：uvicorn 回的是小写键（content-type），
    我第一版写 hd.get("Content-Type") → 永远 None，一口气假报了 8 条"失败"。
    """
    for k, v in (hd or {}).items():
        if k.lower() == name.lower():
            return v
    return default


def Q(s):
    """把含中文的路径段编码好再拼 URL。

    ★ 检查器自己踩过的第二个坑：非 ASCII 直接塞进 URL 会让 urllib 抛
    UnicodeEncodeError（请求根本没发出去），我第一版把它当成了"站点没返回 404"。
    """
    return urllib.parse.quote(str(s), safe="")


def bundle(path="/"):
    """取页面 + 它引用的**同源** css/js（含 ES 模块的 import 图），
    返回 (html, 合并文本, 资源清单, 总字节)。

    ★ 检查器自己踩过的第三个坑（2026-09-18 重构时暴露）：
      原先这一节写的是「GET / 页面体积 > 30KB」和「html 里有 function openGen」。
      这两个断言把「CSS/JS 内联在 index.html 里」当成了「页面有内容」的代理指标。
      重构把内联外置到 /static/ 之后，HTML 变小是**正确结果**，断言却红了 ——
      典型的"检查器假设过时"，不是站点坏了。

    ★ 第四个坑（阶段 2b 拆 ES 模块时）：只跟一层外链不够。
      index.html 只直接引用 main.js，另外 7 个模块靠 import 链到达；
      只取一层会少算 7/8 的代码量，还会漏掉模块内部引用的资源
      （/gen/static/gen_ui.css 就在 views.js 里，不在 HTML 里）。
      所以这里要顺着 import 图递归走。

      修法不是放宽阈值，而是让检查器去解析页面引用的外置资源再合并。
      这样反而验得更实：顺带确认了每个外链、每个 import 都真的取得到。
    """
    st, hd, b, t = req("GET", path)
    html = T(b)
    parts = [html]
    assets = []
    total = len(b)
    seen = set()
    todo = []
    for m in re.finditer(r'<(?:link[^>]+href|script[^>]+src)=["\']([^"\']+)["\']', html):
        u = m.group(1)
        if u.startswith("/") and not u.startswith("//"):
            todo.append(u)
    while todo:
        u = todo.pop()
        if u in seen:
            continue
        seen.add(u)
        s2, _h2, b2, _t2 = req("GET", u)
        assets.append((u, s2, len(b2)))
        if s2 != 200:
            continue
        txt = T(b2)
        parts.append(txt)
        total += len(b2)
        if u.endswith(".js"):
            for dep in re.findall(r"""from\s*['"]\./([\w.-]+)['"]""", txt):
                todo.append(u.rsplit("/", 1)[0] + "/" + dep)
    return html, "\n".join(parts), assets, total


# ============================================================ [1] 页面与静态资源

def test_pages(skip_slow):
    sec("[1] 页面与静态资源（含前端可达性、缓存头、目录穿越）")
    st, hd, b, t = req("GET", "/")
    html = T(b)
    check("GET / 返回 200", st == 200, st)
    check("GET / 是 HTML", "text/html" in hget(hd, "Content-Type"), hget(hd, "Content-Type"))
    # 2026-09-18 重构：CSS/JS 已从 index.html 外置，所以「页面体积」和「页面里有某函数」
    # 都要按「页面 + 它引用的外链」来算，否则断言测的是内联实现而不是页面内容。
    html2, merged, assets, total = bundle("/")
    check("首页外链全部可取得", all(s == 200 for _u, s, _n in assets),
          " ".join("%s=%s" % (u, s) for u, s, _n in assets))
    check("首页 + 外置资源总体积 > 30KB", total > 30000, "%d 字节（HTML %d + 外链 %d）"
          % (total, len(b), total - len(b)))
    check("首页含「报告审核」入口", "报告审核" in html)
    check("首页含「报告编制」入口", "报告编制" in html)
    check("首页含「知识图谱」入口", "知识图谱" in html)
    check("首页有 auditView 容器", 'id="auditView"' in html)
    check("首页有 genView 容器", 'id="genView"' in html)
    check("首页有 openGen()（页内切换，不跳转）", "openGen" in merged)
    check("首页不再有 window.open('/gen') 跳转", "window.open('/gen'" not in merged and 'window.open("/gen"' not in merged)
    check("首页引用了 gen_ui.css", "/gen/static/gen_ui.css" in merged)
    check("首页引用了 audit_ui.css", "/audit/static/audit_ui.css" in merged)
    timed("GET /", t)

    st, hd, b, t = req("GET", "/gen")
    g = T(b)
    check("GET /gen 返回 200", st == 200, st)
    check("/gen 是薄壳（引用同一份模块）", "/gen/static/gen_ui.js" in g)
    check("/gen 自身不含 ge-shell 模板（不会分叉出第二份 UI）", "ge-shell" not in g)
    check("GET /gen/ 尾斜杠也 200", req("GET", "/gen/")[0] == 200)

    st, hd, b, t = req("GET", "/audit")
    a = T(b)
    check("GET /audit 返回 200", st == 200, st)
    # 阶段 3 起 /audit 直接引的是外壳入口 audit_page.js，
    # 它再 import audit_ui.js —— 所以这里改查外壳，模块关系另有一条断言。
    check("/audit 引用 audit_page.js（外壳入口）", "/audit/static/audit_page.js" in a)
    check("/audit 引用外壳 CSS", "/audit/static/audit_page.css" in a)
    check("GET /audit/ 尾斜杠也 200", req("GET", "/audit/")[0] == 200)

    for path, ctype, minlen in [
        ("/gen/static/gen_ui.js", "javascript", 20000),
        ("/gen/static/gen_ui.css", "text/css", 10000),
        ("/audit/static/audit_ui.js", "javascript", 15000),
        ("/audit/static/audit_ui.css", "text/css", 8000),
        # 2026-09-18 重构新增：首页自己的静态资源（阶段 2a 抽 CSS，阶段 2b 拆 ES 模块）
        ("/static/app.css", "text/css", 10000),
        ("/static/js/util.js", "javascript", 800),
        ("/static/js/message.js", "javascript", 5000),
        ("/static/js/image.js", "javascript", 2500),
        ("/static/js/kg.js", "javascript", 9000),
        ("/static/js/views.js", "javascript", 3000),
        ("/static/js/store.js", "javascript", 1800),
        ("/static/js/ask.js", "javascript", 3500),
        ("/static/js/main.js", "javascript", 1800),
        # 阶段 3 新增：独立页 /audit 的外壳资源（原来内联在 audit.html 里）
        ("/audit/static/audit_page.css", "text/css", 1200),
        ("/audit/static/audit_page.js", "javascript", 300),
    ]:
        st, hd, b, t = req("GET", path)
        check("GET %s → 200" % path, st == 200, st)
        check("  %s 类型正确" % path.split("/")[-1], ctype in hget(hd, "Content-Type"), hget(hd, "Content-Type"))
        check("  %s 非空（>%d 字节）" % (path.split("/")[-1], minlen), len(b) > minlen, len(b))
        check("  %s 带 no-cache" % path.split("/")[-1], "no-cache" in hget(hd, "Cache-Control"),
              hget(hd, "Cache-Control"))

    # ---- ES 模块图（阶段 2b）：从 main.js 出发把 import 图走一遍 ----
    # 这条比「逐个文件 200」强得多：它能抓到「某个模块少传了 / 改名了 /
    # import 路径写错了」——那类错在单文件检查里全是绿的，浏览器里却整页白屏。
    check("首页用 type=module 加载入口", 'type="module"' in html and "/static/js/main.js" in html)
    _seen, _todo, _bad = set(), ["/static/js/main.js"], []
    while _todo:
        _u = _todo.pop()
        if _u in _seen:
            continue
        _seen.add(_u)
        _s2, _h2, _b2, _t2 = req("GET", _u)
        if _s2 != 200:
            _bad.append("%s=%s" % (_u, _s2))
            continue
        for _dep in re.findall(r"""from\s*['"]\./([\w.-]+)['"]""", T(_b2)):
            _todo.append("/static/js/" + _dep)
    check("ES 模块图完整（每个 import 都能解析到 200）", not _bad,
          " ".join(_bad) or "%d 个模块全部可达" % len(_seen))
    check("ES 模块图无孤立文件（8 个模块都被引用）", len(_seen) == 8, "可达 %d 个" % len(_seen))

    # ---- 阶段 3：两个子界面模块化 ----
    # 这几条是「重构有没有真落地」的守门员：如果哪天有人把 gen_ui.js 改回传统脚本、
    # 或者把 var 写回来，这里立刻红。
    _g = T(req("GET", "/gen/static/gen_ui.js")[2])
    check("gen_ui.js 是 ES 模块（export mountGenUI）",
          re.search(r"^export\s+function\s+mountGenUI", _g, re.M) is not None)
    check("gen_ui.js 不再挂 window.mountGenUI", "window.mountGenUI" not in _g)
    check("gen_ui.js 无 var（已全改 const/let）",
          re.search(r"(?<![.\w$])var\s+[A-Za-z_$]", _g) is None)
    check("gen_ui.js 无 == 松散比较（eqeqeq）",
          re.search(r"[^=!<>]==[^=]", _g) is None)
    _au = T(req("GET", "/audit/static/audit_ui.js")[2])
    check("audit_ui.js 是 ES 模块（export mountAuditUI）",
          re.search(r"^export\s+function\s+mountAuditUI", _au, re.M) is not None)
    check("audit_ui.js 不再挂 window.mountAuditUI", "window.mountAuditUI" not in _au)
    check("audit_ui.js 无 var",
          re.search(r"(?<![.\w$])var\s+[A-Za-z_$]", _au) is None)
    _ap = T(req("GET", "/audit/static/audit_page.js")[2])
    check("audit_page.js 用 import 引 audit_ui.js", "from './audit_ui.js'" in _ap)
    check("audit_page.js 真的调了 mountAuditUI", "mountAuditUI(" in _ap)
    _v = T(req("GET", "/static/js/views.js")[2])
    check("views.js 用动态 import 加载子界面（不再是 <script> 注入）",
          "import('/gen/static/gen_ui.js')" in _v and "import('/audit/static/audit_ui.js')" in _v)
    check("views.js 不再动态插 script 标签", "createElement('script')" not in _v)
    check("/gen 用 type=module 加载", 'type="module"' in T(req("GET", "/gen")[2]))
    _ah = T(req("GET", "/audit")[2])
    check("/audit 用 type=module 加载", 'type="module"' in _ah)
    check("/audit 无内联 style/script",
          re.search(r"<(?:style|script)(?![^>]*\bsrc=)[^>]*>[^<]", _ah) is None)

    # 白名单 + 穿越
    check("GET /gen/static/nope.js → 404", req("GET", "/gen/static/nope.js")[0] == 404)
    check("GET /audit/static/nope.css → 404", req("GET", "/audit/static/nope.css")[0] == 404)
    check("GET /static/nope.css → 404（首页白名单）", req("GET", "/static/nope.css")[0] == 404)
    check("GET /static/../routes.py 被拒（首页穿越）",
          req("GET", "/static/../routes.py")[0] in (400, 404))
    check("GET /static/..%2f..%2froutes.py 被拒（首页编码穿越）",
          req("GET", "/static/..%2f..%2froutes.py")[0] in (400, 404))
    check("GET /gen/static/../gen_routes.py 被拒（穿越）",
          req("GET", "/gen/static/../gen_routes.py")[0] in (400, 404))
    check("GET /gen/static/..%2fgen_routes.py 被拒（编码穿越）",
          req("GET", "/gen/static/..%2fgen_routes.py")[0] in (400, 404))
    check("GET /audit/static/../audit_routes.py 被拒（穿越）",
          req("GET", "/audit/static/../audit_routes.py")[0] in (400, 404))
    check("GET /audit/static/../../etc/passwd 被拒",
          req("GET", "/audit/static/../../etc/passwd")[0] in (400, 404))
    check("GET /audit/static/..%5caudit_routes.py 被拒（反斜杠穿越）",
          req("GET", "/audit/static/..%5caudit_routes.py")[0] in (400, 404))

    st, _, b, _ = req("GET", "/openapi.json")
    note("GET /openapi.json 可匿名访问（HTTP %s）—— 暴露全部接口签名" % st)
    st, _, b, _ = req("GET", "/docs")
    note("GET /docs 可匿名访问（HTTP %s）—— 暴露交互式接口文档" % st)


# ============================================================ [2] 站点基础接口

def test_site_api(skip_slow):
    sec("[2] 站点基础接口：健康 / 知识图谱 / 问答 / 原文")
    st, _, b, t = req("GET", "/health")
    d = J(b) or {}
    check("GET /health → 200", st == 200, st)
    check("  /health 有 status/model", d.get("status") == "ok" and bool(d.get("model")), d.get("model"))
    check("  /health 报告 pdf_root 存在", d.get("pdf_root_exists") == "True", d.get("pdf_root"))
    check("  /health 不泄露密钥（只有来源标记）",
          "intent_key_source" in d and len(str(d.get("intent_key_source"))) < 20, d.get("intent_key_source"))
    timed("GET /health", t)

    st, _, b, t = req("GET", "/kg/stats")
    d = J(b) or {}
    check("GET /kg/stats → 200", st == 200, st)
    check("  图谱 available", d.get("available") is True)
    check("  图谱节点数 > 0", (d.get("nodes") or 0) > 0, d.get("nodes"))
    check("  图谱边数 > 0", (d.get("links") or 0) > 0, d.get("links"))
    timed("GET /kg/stats", t)

    st, _, b, t = req("GET", "/kg/search?query=%E5%8D%B1%E9%99%A9%E5%BA%9F%E7%89%A9&depth=1&limit=40")
    d = J(b) or {}
    check("GET /kg/search（危险废物）→ 200", st == 200, st)
    check("  返回 nodes/links", "nodes" in d and "links" in d, list(d.keys())[:6])
    check("GET /kg/search 空 query 也 200", req("GET", "/kg/search")[0] == 200)
    check("GET /kg/search?depth=3 → 422（越界被挡）", req("GET", "/kg/search?depth=3")[0] == 422)
    check("GET /kg/search?limit=5 → 422（低于下限）", req("GET", "/kg/search?limit=5")[0] == 422)
    check("GET /kg/search?query=<201字> → 422（超长被挡）",
          req("GET", "/kg/search?query=" + "a" * 201)[0] == 422)
    timed("GET /kg/search", t)

    # ---- 问答（真调模型，慢）
    check("GET /hybrid_search 缺 query → 422", req("GET", "/hybrid_search")[0] == 422)
    check("GET /hybrid_search query 空串 → 422", req("GET", "/hybrid_search?query=")[0] == 422)
    check("GET /hybrid_search top_k=0 → 422", req("GET", "/hybrid_search?query=x&top_k=0")[0] == 422)
    check("GET /hybrid_search top_k=11 → 422", req("GET", "/hybrid_search?query=x&top_k=11")[0] == 422)
    check("GET /hybrid_search max_tokens=99999 → 422",
          req("GET", "/hybrid_search?query=x&max_tokens=99999")[0] == 422)
    st, _, b, t = req("GET", "/hybrid_search?query=x&report=photo")
    check("GET /hybrid_search?report=photo → 400 且提示要上传图片",
          st == 400 and "图片" in T(b), "%s %s" % (st, T(b)[:80]))

    st, _, b, t = req("POST", "/hybrid_search", data={})
    # 2026-09-18 错误码改造后，空 query 由 pipeline.answer_query 抛 E_QUERY_EMPTY，
    # 文案是"请先输入问题或上传图片"（比原来的"query不能为空"更可操作）。
    # 这里改成断言**错误码**——比匹配中文文案更稳：文案以后还能改，码不能改。
    _code = ""
    try:
        _code = json.loads(T(b)).get("code", "")
    except Exception:                                             # noqa: BLE001
        pass
    check("POST /hybrid_search 空体 → 400 + E_QUERY_EMPTY",
          st == 400 and _code == "E_QUERY_EMPTY",
          "%s %s %s" % (st, _code or "（无码）", T(b)[:50]))
    st, _, b, t = req("POST", "/hybrid_search", data={"query": "x", "top_k": 0})
    check("POST /hybrid_search top_k 越界 → 422", st == 422, st)
    st, _, b, t = req("POST", "/hybrid_search", data={"image": "notadataurl"})
    check("POST /hybrid_search 非 data URL 图片 → 400",
          st == 400 and "图片" in T(b), "%s %s" % (st, T(b)[:70]))

    st, _, b, t = req("POST", "/hybrid_search/stream", data={}, timeout=30)
    check("POST /hybrid_search/stream 空体 → 400（状态码在流开始前就发对）", st == 400, st)

    src_md = None
    cand = []          # 候选来源（供 /doc 正向用例），不止第一条
    if not skip_slow:
        q = "危险废物贮存污染控制标准对贮存设施的要求"
        st, _, b, t = req("GET", "/hybrid_search?query=" + urllib.parse.quote(q), timeout=240)
        d = J(b) or {}
        check("GET /hybrid_search（真实专业问题）→ 200", st == 200,
              "HTTP %s %s" % (st, str(d.get("detail"))[:120]))
        if st == 200:
            check("  返回 answer 非空", bool((d.get("answer") or "").strip()), len(d.get("answer") or ""))
            check("  返回 sources 列表", isinstance(d.get("sources"), list), type(d.get("sources")).__name__)
            # ★ 收集**多条**候选，而不是只取第一条。
            # 原来只取第一条，而"第一条有没有 PDF"完全看检索运气 ——
            # 实测 /data/fagui_pdf/环评报告/ 下 0 个 PDF，索引里却有 592 条环评报告，
            # 检索一旦命中环评报告，这条用例就必然误报失败（那就是一直记着的 [009]）。
            for s in (d.get("sources") or []):
                if str(s.get("source", "")).lower().endswith(".md"):
                    cand.append(s["source"])
            src_md = cand[0] if cand else None
            note("RAG 命中来源 %d 条，route=%s，latency=%s" % (len(d.get("sources") or []),
                                                             d.get("route"), d.get("latency")))
        timed("GET /hybrid_search（含模型）", t)

        # SSE 真跑一次
        st, hd, b, t = req("POST", "/hybrid_search/stream",
                           data={"query": "生活垃圾焚烧飞灰属于危险废物吗"}, timeout=240)
        sse = T(b)
        check("POST /hybrid_search/stream → 200", st == 200, st)
        check("  Content-Type 是 text/event-stream", "text/event-stream" in hget(hd, "Content-Type"),
              hget(hd, "Content-Type"))
        check("  SSE 有 event: 帧", "event:" in sse, sse[:60].replace("\n", "|"))
        check("  SSE 有 data: 帧", "data:" in sse)
        check("  SSE 以空行分帧（\\n\\n）", "\n\n" in sse)
        if "event: error" in sse:
            note("流式通道把后端故障作为 error 帧吐出来了：%s"
                 % sse.split("event: error", 1)[1][:140].replace("\n", " "))
        timed("POST /hybrid_search/stream（含模型）", t)

    # ---- /doc 原文
    check("GET /doc 缺 source → 422", req("GET", "/doc")[0] == 422)
    st, _, b, t = req("GET", "/doc?source=/etc/passwd")
    check("GET /doc 非 .md → 400", st == 400, "%s %s" % (st, T(b)[:70]))
    st, _, b, t = req("GET", "/doc?source=" + urllib.parse.quote("../../../../etc/passwd.md"))
    check("GET /doc 目录穿越 → 400「路径越界」", st == 400 and "越界" in T(b), "%s %s" % (st, T(b)[:70]))
    st, _, b, t = req("GET", "/doc?source=" + Q("绝对不存在的文件.md"))
    check("GET /doc 不存在的 .md → 404", st == 404, st)

    # ★ 2026-09-18 修：原来这条写的是"真实来源 → 200 PDF"，
    # 隐含假设"索引里的来源都有 PDF"。这个假设是**错的**：
    # 环评报告 592 条 .md 一条 PDF 都没有（原始 PDF 从没上传到服务器）。
    # 真正的不变量是「每条索引来源总能以某种方式打开」——
    # 有 PDF 走 /doc，没 PDF 走 /doc/text（新增的文本回退）。
    if cand:
        n_pdf = n_text = n_neither = 0
        for s in cand[:8]:
            st, hd, b, t = req("GET", "/doc/info?source=" + urllib.parse.quote(s))
            info = J(b) or {}
            if st != 200:
                check("来源 %s 的 /doc/info → 200" % s[-26:], False, "HTTP %s" % st)
                continue
            if info.get("has_pdf"):
                n_pdf += 1
                st2, hd2, b2, t2 = req("GET", "/doc?source=" + urllib.parse.quote(s), timeout=180)
                check("有 PDF 的来源 /doc → 200 且是 PDF（…%s）" % s[-26:],
                      st2 == 200 and b2[:4] == b"%PDF",
                      "%s %s" % (st2, hget(hd2, "Content-Type")))
                timed("GET /doc（真实 PDF）", t2)
            elif info.get("has_md"):
                n_text += 1
                st2, _, b2, t2 = req("GET", "/doc/text?source=" + urllib.parse.quote(s), timeout=180)
                d2 = J(b2) or {}
                check("只有文本的来源 /doc/text → 200 且有正文（…%s）" % s[-26:],
                      st2 == 200 and len(d2.get("text") or "") > 200,
                      "HTTP %s，正文 %d 字" % (st2, len(d2.get("text") or "")))
            else:
                n_neither += 1
                check("来源 %s 至少有一种打开方式" % s[-26:], False, "既无 PDF 也无文本")
        check("★ 每条抽样来源都能打开（PDF 或文本）", n_neither == 0,
              "带 PDF %d 条 / 仅文本 %d 条 / 都打不开 %d 条" % (n_pdf, n_text, n_neither))
        # 反向断言：确实至少走过一条正向路径，否则上面的循环可能是空转
        check("反向：抽样里至少有一条真的打开了", (n_pdf + n_text) > 0,
              "pdf=%d text=%d" % (n_pdf, n_text))
        # 说明：本套件只做 HTTP 探测，抽样里是否恰好含"仅文本"的来源取决于检索结果。
        # 环评报告（592 条只有 .md、没有 PDF）那条路径由服务端的
        # 查原文回退_实测.py 专门覆盖 —— 它能直接读 /data 目录挑样本。
        if n_text == 0:
            note("本次抽样的来源都带 PDF，未覆盖文本回退路径；"
                 "该路径由 查原文回退_实测.py 专门验证")
    else:
        note("没拿到 .md 来源，/doc 正向用例未覆盖（--skip-slow 下正常）")


# ============================================================ [3] 审核接口

def test_audit(skip_slow):
    sec("[3] 报告审核接口：清单 / 运行 / 进度 / 原文 / 人工复核 / 导出")
    st, _, b, t = req("GET", "/audit/api/health")
    d = J(b) or {}
    check("GET /audit/api/health → 200 且 ok", st == 200 and d.get("ok") is True, d.get("error"))
    check("  审核引擎 page 存在", d.get("page") is True)
    check("  判据目录存在", d.get("判据目录存在") is True, d.get("判据目录"))
    timed("GET /audit/api/health", t)

    st, _, b, t = req("GET", "/audit/api/reports")
    d = J(b) or {}
    reps = d.get("reports") or []
    check("GET /audit/api/reports → 200", st == 200, st)
    check("  报告清单非空", len(reps) > 0, "%d 份" % len(reps))
    check("  每份都有 name/size", all(r.get("name") and r.get("size") for r in reps))
    timed("GET /audit/api/reports", t)
    if not reps:
        return None
    name = reps[0]["name"]
    valid_item = None   # 从真实结果里取一个合法审核项名，后面测 save 用它，别自己编名字

    check("POST /audit/api/run 缺 name → 422", req("POST", "/audit/api/run")[0] == 422)
    st, _, b, t = req("POST", "/audit/api/run?name=" + urllib.parse.quote("不存在的报告.pdf"))
    check("POST /audit/api/run 不在清单 → 404", st == 404, st)
    st, _, b, t = req("POST", "/audit/api/run?name=" + urllib.parse.quote(name) + "&use_llm=false")
    d = J(b) or {}
    check("POST /audit/api/run（真实报告）→ 200 拿到 job", st == 200 and d.get("job"), st)
    job = d.get("job")
    if job:
        st, _, b, t = req("GET", "/audit/api/job/" + job, timeout=30)
        d2 = J(b) or {}
        check("GET /audit/api/job/<job> → 200 有 stage/pct", st == 200 and "stage" in d2,
              "%s %s" % (st, d2.get("stage")))
        # 轮询到完成（use_llm=false 只走正则，应该较快）
        t0 = time.time()
        done = None
        while time.time() - t0 < 300:
            st, _, b, _ = req("GET", "/audit/api/job/" + job, timeout=30)
            d2 = J(b) or {}
            if d2.get("done"):
                done = d2
                break
            time.sleep(2)
        check("  任务跑到 done", bool(done), "%.0fs" % (time.time() - t0))
        if done:
            check("  没有 error", not done.get("error"), str(done.get("error"))[:100])
            res = done.get("result") or {}
            items = res.get("items") or []
            check("  结果恰好 18 项审核项", len(items) == 18, "%d 项" % len(items))
            if items:
                valid_item = items[0]["审核项"]
            check("  每项都有 审核项/AI审核/理由", all(
                it.get("审核项") and it.get("AI审核") and it.get("理由") is not None for it in items))
            check("  统计里有结论分布", bool(res.get("统计")), res.get("统计"))
            timed("POST /audit/api/run + 轮询到完成（use_llm=false）", round(time.time() - t0, 1))
    check("GET /audit/api/job/<乱码> → 404", req("GET", "/audit/api/job/zzzz")[0] == 404)

    st, hd, b, t = req("GET", "/audit/api/pdf/" + urllib.parse.quote(name), timeout=180)
    check("GET /audit/api/pdf/<真实报告> → 200 PDF", st == 200 and b[:4] == b"%PDF",
          "%s %d 字节" % (st, len(b)))
    check("GET /audit/api/pdf/<不在清单> → 404",
          req("GET", "/audit/api/pdf/nope.pdf")[0] == 404)
    check("GET /audit/api/pdf/../audit_routes.py → 404",
          req("GET", "/audit/api/pdf/..%2faudit_routes.py")[0] == 404)
    timed("GET /audit/api/pdf（真实 PDF）", t)

    st, _, b, t = req("GET", "/audit/api/review/" + urllib.parse.quote(name))
    d = J(b) or {}
    check("GET /audit/api/review/<真实> → 200", st == 200 and d.get("ok") is True, st)
    # 用 %2f 塞穿越串时，Starlette 在路由层就匹配不上（404），根本进不到 _safe_name 的 400。
    # 404 同样是"拒绝"，比 400 还早，不算缺陷 —— 第一版我按 400 断言，是期望写窄了。
    check("GET /audit/api/review/..%2fx 被拒（404 或 400）",
          req("GET", "/audit/api/review/..%2fx")[0] in (400, 404))
    check("GET /audit/api/review/.hidden → 400",
          req("GET", "/audit/api/review/.hidden")[0] == 400)

    st, _, b, t = req("POST", "/audit/api/save", data={"name": "../evil.pdf", "items": {}})
    check("POST /audit/api/save 名字带穿越 → 400", st == 400, st)
    st, _, b, t = req("POST", "/audit/api/save", data={"name": name, "items": {"瞎写的审核项": {"人工修改": "无问题"}}})
    check("POST /audit/api/save 未知审核项 → 400", st == 400 and "审核项不存在" in T(b),
          "%s %s" % (st, T(b)[:80]))
    # 用一个**真实存在**的审核项名 + 非法状态值，才是真的在验"状态白名单"。
    # （第一版我自己编了个项名，结果它因为"项不存在"而 400，断言通过了但验的不是那件事。）
    if valid_item:
        st, _, b, t = req("POST", "/audit/api/save",
                          data={"name": name, "items": {valid_item: {"人工修改": "随便写的状态"}}})
        check("POST /audit/api/save 非法结论状态 → 400「结论状态非法」",
              st == 400 and "结论状态非法" in T(b), "%s %s" % (st, T(b)[:90]))
        st, _, b, t = req("POST", "/audit/api/save",
                          data={"name": name, "items": {valid_item: {"人工修改": "优化调整建议"}}})
        check("POST /audit/api/save 合法状态 → 200 且 saved=1",
              st == 200 and (J(b) or {}).get("saved") == 1, "%s %s" % (st, T(b)[:90]))
        check("  保存后 review 能读回（刷新不丢）",
              (J(req("GET", "/audit/api/review/" + urllib.parse.quote(name))[2]) or {})
              .get("items", {}).get(valid_item, {}).get("人工修改") == "优化调整建议")
    else:
        note("没拿到合法审核项名，save 的状态白名单用例未覆盖")

    st, _, b, t = req("GET", "/audit/api/export/" + urllib.parse.quote(name) + "?fmt=csv")
    d = J(b) or {}
    check("GET /audit/api/export?fmt=csv → 200", st == 200 and d.get("file"), "%s %s" % (st, d.get("file")))
    csv_name = d.get("file")
    st, _, b, t = req("GET", "/audit/api/export/" + urllib.parse.quote(name) + "?fmt=json")
    d = J(b) or {}
    check("GET /audit/api/export?fmt=json → 200", st == 200 and d.get("file"), d.get("file"))
    check("GET /audit/api/export/<没有结果> → 404",
          req("GET", "/audit/api/export/" + Q("绝对没有这份报告.pdf"))[0] == 404)
    if csv_name:
        st, hd, b, t = req("GET", "/audit/api/download/" + urllib.parse.quote(csv_name))
        check("GET /audit/api/download/<导出csv> → 200", st == 200, st)
        check("  CSV 带 UTF-8 BOM（Excel 不乱码）", b[:3] == b"\xef\xbb\xbf", b[:3])
        check("  CSV 含 18 项表头列", "审核项" in T(b) and "最终结论" in T(b))
        timed("GET /audit/api/download（CSV）", t)
    check("GET /audit/api/download/..%2fx 被拒（404 或 400）",
          req("GET", "/audit/api/download/..%2fx")[0] in (400, 404))
    check("GET /audit/api/download/没有.csv → 404",
          req("GET", "/audit/api/download/" + Q("没有.csv"))[0] == 404)
    return name


# ============================================================ [4] 生成接口

def test_gen(skip_slow):
    sec("[4] 报告编制接口：健康 / 模板 / 样例 / 历史 / 对话 / 生成 / 预览 / 下载 / 重置")
    st, _, b, t = req("GET", "/gen/api/health")
    d = J(b) or {}
    check("GET /gen/api/health → 200 且 ok", st == 200 and d.get("ok") is True, d.get("error"))
    check("  字段数 39", d.get("字段数") == 39, d.get("字段数"))
    check("  docx 可用", str(d.get("docx")) != "未安装（无法生成 Word）", d.get("docx"))
    check("  判据文件齐全", len(d.get("判据文件") or []) >= 2, d.get("判据文件"))
    timed("GET /gen/api/health", t)

    st, hd, b, t = req("GET", "/gen/api/template")
    d = J(b) or {}
    check("GET /gen/api/template → 200 JSON", st == 200 and isinstance(d, (dict, list)),
          "%s %s" % (st, hget(hd, "Content-Type")))

    st, _, b, t = req("GET", "/gen/api/samples/" + urllib.parse.quote("演示_虚构项目_填报.json"))
    d = J(b) or {}
    sample = d.get("data")
    check("GET /gen/api/samples/<真实样例> → 200", st == 200 and isinstance(sample, dict), st)
    check("GET /gen/api/samples/nope.json → 404", req("GET", "/gen/api/samples/nope.json")[0] == 404)
    check("GET /gen/api/samples 穿越 → 404",
          req("GET", "/gen/api/samples/..%2f..%2f..%2fetc%2fpasswd")[0] in (400, 404))

    st, _, b, t = req("GET", "/gen/api/outputs")
    d = J(b) or {}
    files = d.get("files") or []
    check("GET /gen/api/outputs → 200", st == 200, st)
    check("  历史报告非空（归档不删）", len(files) > 0, "%d 份" % len(files))
    check("  每份有 name/size/mtime", all(f.get("name") and f.get("size") is not None and f.get("mtime")
                                        for f in files))
    check("  只列 .docx（不混入模板/临时文件）", all(f["name"].endswith(".docx") for f in files))
    timed("GET /gen/api/outputs", t)
    old_file = files[-1]["name"] if files else None

    st, _, b, t = req("GET", "/gen/api/jobs")
    check("GET /gen/api/jobs → 200", st == 200 and "jobs" in (J(b) or {}), st)
    check("GET /gen/api/job/<乱码> → 404", req("GET", "/gen/api/job/zzzz")[0] == 404)
    check("GET /gen/api/download/<乱码> → 404", req("GET", "/gen/api/download/zzzz")[0] == 404)
    check("GET /gen/api/preview/<乱码> → 404", req("GET", "/gen/api/preview/zzzz")[0] == 404)
    check("GET /gen/api/preview_file/<乱码> → 404", req("GET", "/gen/api/preview_file/nope.docx")[0] == 404)
    check("GET /gen/api/preview_file 穿越 → 404",
          req("GET", "/gen/api/preview_file/..%2f..%2f..%2fetc%2fpasswd")[0] in (400, 404))
    check("GET /gen/api/output/<乱码> → 404", req("GET", "/gen/api/output/nope.docx")[0] == 404)
    check("GET /gen/api/output 穿越 → 404",
          req("GET", "/gen/api/output/..%2f..%2fgen_routes.py")[0] in (400, 404))

    # ---- 表单式提交（纯代码路径，确定性）
    st, _, b, t = req("POST", "/gen/api/run", data={})
    check("POST /gen/api/run 空体 → 400", st == 400, "%s %s" % (st, T(b)[:70]))
    st, _, b, t = req("POST", "/gen/api/run", data={"data": "{不是合法 JSON"})
    check("POST /gen/api/run 非法 JSON 串 → 400", st == 400 and "合法 JSON" in T(b), T(b)[:80])
    st, _, b, t = req("POST", "/gen/api/run", data={"data": [1, 2, 3]})
    check("POST /gen/api/run 非对象 → 400", st == 400 and "JSON 对象" in T(b), T(b)[:80])
    st, _, b, t = req("POST", "/gen/api/run", data={"sample": "nope.json"})
    check("POST /gen/api/run 不存在的样例 → 404", st == 404, st)

    if sample:
        # XSS 探针：项目名称里塞 HTML/脚本，预览必须转义
        xss = dict(sample)
        xss["项目名称"] = '<img src=x onerror=alert(1)>"><script>alert(2)</script>'
        st, _, b, t = req("POST", "/gen/api/run", data={"data": xss, "model": False})
        d = J(b) or {}
        job = d.get("job")
        check("POST /gen/api/run（含 HTML 的项目名称）→ 200", st == 200 and job, st)
        if job:
            t0 = time.time()
            res = None
            while time.time() - t0 < 300:
                st, _, b, _ = req("GET", "/gen/api/job/" + job, timeout=30)
                jj = (J(b) or {}).get("job") or {}
                if jj.get("status") in ("done", "rejected", "failed"):
                    res = jj
                    break
                time.sleep(1.5)
            check("  任务完成（status=done）", (res or {}).get("status") == "done",
                  "%s %.0fs" % ((res or {}).get("status"), time.time() - t0))
            if (res or {}).get("status") == "done":
                check("  产物有文件名与大小", bool(res.get("file")) and (res.get("size") or 0) > 10000,
                      "%s %s 字节" % (res.get("file"), res.get("size")))
                st, hd, b, t = req("GET", "/gen/api/preview/" + job, timeout=120)
                pv = T(b)
                check("  GET /gen/api/preview/<job> → 200 HTML", st == 200 and "<html" not in pv[:200],
                      "%s %d 字节" % (st, len(b)))
                check("  ★ 预览转义了 <script>（无 XSS）", "<script>alert(2)" not in pv)
                check("  ★ 预览转义了 onerror（无 XSS）", "onerror=alert(1)>" not in pv)
                check("  预览里能看到转义后的实体", "&lt;script&gt;" in pv or "&lt;img" in pv)
                check("  预览含 交付件同源 说明", "交付件本身" in pv)
                st, hd, b2, t = req("GET", "/gen/api/download/" + job, timeout=120)
                check("  GET /gen/api/download/<job> → 200 docx", st == 200 and b2[:2] == b"PK",
                      "%s %d 字节" % (st, len(b2)))
                check("  下载字节数 == 任务报告的大小", len(b2) == (res.get("size") or -1),
                      "%d vs %s" % (len(b2), res.get("size")))
                check("  下载 Content-Disposition 带文件名",
                      "filename" in hget(hd, "Content-Disposition").lower(),
                      hget(hd, "Content-Disposition"))
                timed("POST /gen/api/run（表单式，纯代码）+ 轮询", round(time.time() - t0, 1))
                check("  ★ 自审未报「存在问题」（草稿不该自我否决）",
                      ((res.get("自审") or {}).get("分布") or {}).get("存在问题", 0) == 0,
                      (res.get("自审") or {}).get("分布"))

    # ---- 历史报告：老文件能预览 + 下载，且字节数与列表一致
    if old_file:
        st, hd, b, t = req("GET", "/gen/api/preview_file/" + urllib.parse.quote(old_file), timeout=180)
        check("GET /gen/api/preview_file/<历史报告> → 200 HTML", st == 200 and b"pp-page" in b,
              "%s %d 字节" % (st, len(b)))
        st, hd, b2, t = req("GET", "/gen/api/output/" + urllib.parse.quote(old_file), timeout=180)
        listed = [f["size"] for f in files if f["name"] == old_file]
        check("GET /gen/api/output/<历史报告> → 200 docx", st == 200 and b2[:2] == b"PK", st)
        check("  下载字节数 == 列表里的大小", listed and len(b2) == listed[0],
              "%d vs %s" % (len(b2), listed))
        timed("GET /gen/api/preview_file + output（历史报告）", t)

    # ---- 对话式
    st, _, b, t = req("POST", "/gen/api/chat/start", data={"text": "太短"})
    check("POST /gen/api/chat/start 文本过短 → 400", st == 400, "%s %s" % (st, T(b)[:70]))
    st, _, b, t = req("POST", "/gen/api/chat/answer", data={"session": "zzzz"})
    check("POST /gen/api/chat/answer 会话不存在 → 404", st == 404, st)
    st, _, b, t = req("POST", "/gen/api/chat/skip", data={"session": "zzzz"})
    check("POST /gen/api/chat/skip 会话不存在 → 404", st == 404, st)
    st, _, b, t = req("GET", "/gen/api/chat/state/zzzz")
    check("GET /gen/api/chat/state/<乱码> → 404", st == 404, st)
    st, _, b, t = req("POST", "/gen/api/chat/generate", data={"session": "zzzz"})
    check("POST /gen/api/chat/generate 会话不存在 → 404", st == 404, st)
    st, _, b, t = req("POST", "/gen/api/chat/reset", data={})
    d = J(b) or {}
    check("POST /gen/api/chat/reset 空会话 → 200 且幂等（已清理=false）",
          st == 200 and d.get("已清理") is False, d)
    st, _, b, t = req("POST", "/gen/api/chat/reset", data={"session": "zzzz"})
    check("POST /gen/api/chat/reset 不存在的会话 → 200 不报错", st == 200, st)

    # ---- 示例轮换
    seen, prev, ok_rot = [], "", True
    for i in range(6):
        st, _, b, t = req("GET", "/gen/api/chat/demo" + ("?exclude=" + urllib.parse.quote(prev) if prev else ""))
        d = J(b) or {}
        txt = d.get("示例") or ""
        if st != 200 or not txt:
            ok_rot = False
            break
        if txt.strip() == prev.strip():
            ok_rot = False
        seen.append(txt)
        prev = txt
    check("GET /gen/api/chat/demo 连续 6 次都 200 且有内容", ok_rot, len(seen))
    check("  示例条数 > 1（不是写死一条）", len(set(seen)) > 1, "%d 条不同" % len(set(seen)))
    check("  不会连着重复同一条（exclude 生效）", ok_rot)
    st, _, b, t = req("GET", "/gen/api/chat/demo")
    d = J(b) or {}
    check("  返回序号/总数（页面显示「第 n / N 个」）",
          d.get("序号") and d.get("总数") and d.get("总数") >= 5, "%s/%s" % (d.get("序号"), d.get("总数")))
    check("  示例标明是虚构的", "虚构" in (d.get("示例") or "") or "虚构" in (d.get("说明") or ""))

    if skip_slow:
        return
    # ---- 对话全流程（真调模型抽取）
    # 项目名称故意带【站点测试】前缀：本套件每次跑都会真的生成 Word 落进生产目录，
    # 带上稳定标记，跑完就能用 归档测试产物.py 精确移走（移动不删除），不污染用户的历史列表。
    desc = ("【站点测试】某公司拟建一条年产 3000 吨塑料制品生产线，属于新建项目，"
            "总投资 900 万元，其中环保投资 60 万元，用地面积 2500 平方米。"
            "注塑工序产生有机废气，经集气罩收集后由活性炭吸附装置处理，15 米排气筒排放。"
            "厂界西侧 200 米为红星村，约 80 户 260 人。生活污水经化粪池后排入市政管网，"
            "冷却水循环使用不外排。项目尚未开工建设。")
    st, _, b, t = req("POST", "/gen/api/chat/start", data={"text": desc}, timeout=240)
    d = J(b) or {}
    sid = d.get("session")
    check("POST /gen/api/chat/start（真实描述）→ 200 且拿到会话", st == 200 and bool(sid),
          "%s %s" % (st, d.get("error")))
    timed("POST /gen/api/chat/start（含模型抽取）", t)
    if sid:
        check("  抽取到事实（已知非空）", len(d.get("已知") or []) > 0, "%d 项" % len(d.get("已知") or []))
        check("  每条事实都带原文依据", bool(d.get("依据")), list((d.get("依据") or {}).keys())[:4])
        check("  给出了要问的问题", len(d.get("问题") or []) > 0, "%d 个" % len(d.get("问题") or []))
        check("  报告了还剩多少项", d.get("还剩") is not None, d.get("还剩"))
        qs = d.get("问题") or []
        check("  问题都带 key/中文名/为什么问",
              all(q.get("key") and q.get("中文名") and q.get("为什么问") for q in qs))
        # 答一个 / 跳一个
        if qs:
            q0 = qs[0]
            st, _, b, t = req("POST", "/gen/api/chat/answer",
                              data={"session": sid, "key": q0["key"], "中文名": q0["中文名"],
                                    "类型": q0.get("类型"), "事实名": q0.get("事实名"),
                                    "问题": q0["问题"], "text": "不知道"}, timeout=180)
            d2 = J(b) or {}
            check("POST /gen/api/chat/answer（答「不知道」）→ 200 且不采纳",
                  st == 200 and d2.get("采纳") is False, "%s %s" % (st, d2.get("本次")))
        if len(qs) > 1:
            q1 = qs[1]
            st, _, b, t = req("POST", "/gen/api/chat/skip",
                              data={"session": sid, "问题": q1["问题"], "中文名": q1["中文名"]})
            check("POST /gen/api/chat/skip → 200 且记进对话", st == 200, st)
        st, _, b, t = req("GET", "/gen/api/chat/state/" + sid, timeout=120)
        d3 = J(b) or {}
        check("GET /gen/api/chat/state/<sid> → 200 且对话有记录",
              st == 200 and len(d3.get("对话") or []) >= 1, "%d 轮" % len(d3.get("对话") or []))
        # 生成
        st, _, b, t = req("POST", "/gen/api/chat/generate",
                          data={"session": sid, "model": False}, timeout=120)
        d4 = J(b) or {}
        job = d4.get("job")
        check("POST /gen/api/chat/generate → 200 拿到 job", st == 200 and bool(job), st)
        if job:
            t0 = time.time()
            res = None
            while time.time() - t0 < 600:
                st, _, b, _ = req("GET", "/gen/api/job/" + job, timeout=30)
                jj = (J(b) or {}).get("job") or {}
                if jj.get("status") in ("done", "rejected", "failed"):
                    res = jj
                    break
                time.sleep(2)
            stt = (res or {}).get("status")
            check("  对话式生成跑到 done（缺项不拦，标【需人工补充】）", stt == "done",
                  "%s %.0fs" % (stt, time.time() - t0))
            if stt == "done":
                logs = " ".join(l.get("text", "") for l in (res.get("log") or []))
                check("  日志里出现了【需人工补充】标注", "需人工补充" in logs)
                check("  自审跑过（日志有④自审）", "④自审" in logs or "自审" in logs)
                timed("对话式全流程（抽取→问答→生成→自审）", round(time.time() - t0, 1))
        # 重置
        st, _, b, t = req("POST", "/gen/api/chat/reset", data={"session": sid})
        d5 = J(b) or {}
        check("POST /gen/api/chat/reset（真会话）→ 200 且已清理=true",
              st == 200 and d5.get("已清理") is True, d5)
        check("  重置后 state → 404（会话真没了）", req("GET", "/gen/api/chat/state/" + sid)[0] == 404)
        st, _, b, t = req("GET", "/gen/api/outputs")
        after = len((J(b) or {}).get("files") or [])
        check("  重置**不删**已生成的报告（归档不删）", after >= len(files), "%d → %d" % (len(files), after))


# ============================================================ [5] 并发与稳定性

def test_concurrency():
    sec("[5] 并发与稳定性（同名接口并发、会话隔离）")
    res = []
    lock = threading.Lock()

    # 2026-09-18 查明：这一节偶发的"7/8、共 3.02s"**不是服务端慢**。
    # 证据：
    #   · 把同样的探测放到服务器本机 127.0.0.1 跑 20 轮 × 8 并发 = 160 次，
    #     最慢单个 0.021s，零异常（见 本机并发探测.py）；
    #   · 跨机失败时的耗时**恰好 3.02s**，正是 Linux 的 TCP SYN 重传超时
    #     （初始 RTO 1s + 重传 2s）；
    #   · 同一个 3.02s 在 /kg/stats 和 /audit/api/reports 上随机出现 ——
    #     跟具体端点无关，只跟"哪一次连接丢了包"有关。
    # 所以这一节量到的是**本机到服务器的网络**，不是服务器本身。
    # 对策：失败重试一次。服务端真出错会继续错（断言照样失败），
    #       网络抖一下则这次就过了，并在结果里标明发生过重试。
    def worker(path, n):
        st, _, _, secs = req("GET", path, timeout=60)
        retried = False
        if st != 200:
            time.sleep(0.2)
            st, _, _, secs = req("GET", path, timeout=60)
            retried = True
        with lock:
            res.append((n, st, retried, secs))

    for path, n in [("/health", 20), ("/gen/api/outputs", 10), ("/audit/api/reports", 10), ("/kg/stats", 8)]:
        res.clear()
        ts = [threading.Thread(target=worker, args=(path, i)) for i in range(n)]
        t0 = time.time()
        [t.start() for t in ts]
        [t.join() for t in ts]
        el = round(time.time() - t0, 2)
        good = sum(1 for _, s, _, _ in res if s == 200)
        blips = sum(1 for _, s, r, _ in res if r and s == 200)
        check("并发 %2d 次 GET %s → 全部 200" % (n, path), good == n,
              "%d/%d，共 %.2fs%s"
              % (good, n, el, ("，其中 %d 次跨机网络重试后成功" % blips) if blips else ""))
        timed("并发 %d × %s" % (n, path), el)

    # 会话隔离：同时开 5 个会话，sid 必须互不相同
    sids = []
    lock2 = threading.Lock()

    def start_one(i):
        st, _, b, _ = req("POST", "/gen/api/chat/start",
                          data={"text": "【并发测试 %d】某公司新建一个机械加工车间，"
                                        "总投资 100 万元，环保投资 10 万元，用地 500 平方米，"
                                        "切削液循环使用不外排，项目尚未开工。" % i}, timeout=240)
        d = J(b) or {}
        with lock2:
            sids.append((st, d.get("session")))

    ts = [threading.Thread(target=start_one, args=(i,)) for i in range(5)]
    t0 = time.time()
    [t.start() for t in ts]
    [t.join() for t in ts]
    ok = [s for st, s in sids if st == 200 and s]
    check("并发 5 个会话同时开始 → 全部 200", len(ok) == 5, [st for st, _ in sids])
    check("  5 个 sid 互不相同（会话不串）", len(set(ok)) == len(ok), len(set(ok)))
    timed("并发 5 × chat/start（含模型）", round(time.time() - t0, 2))
    for s in ok:
        req("POST", "/gen/api/chat/reset", data={"session": s})


# ============================================================ main

def main():
    global BASE
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE)
    ap.add_argument("--skip-slow", action="store_true")
    a = ap.parse_args()
    BASE = a.base.rstrip("/")
    print("目标站点：%s" % BASE)
    print("时间：%s" % time.strftime("%Y-%m-%d %H:%M:%S"))

    t0 = time.time()
    test_pages(a.skip_slow)
    test_site_api(a.skip_slow)
    test_audit(a.skip_slow)
    test_gen(a.skip_slow)
    test_concurrency()

    print("\n" + "=" * 64)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    if BAD:
        print("\n失败明细：")
        for x in BAD:
            print("  × %s" % x)
    if WARN:
        print("\n提示（非失败，供决策）：")
        for x in WARN:
            print("  ! %s" % x)
    print("\n耗时最长的 10 项：")
    for label, t in sorted(TIME, key=lambda x: -x[1])[:10]:
        print("  %6.2fs  %s" % (t, label))
    print("总耗时 %.1fs" % (time.time() - t0))
    print("=" * 64)
    return len(BAD)


if __name__ == "__main__":
    sys.exit(main())
