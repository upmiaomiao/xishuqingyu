# -*- coding: utf-8 -*-
"""原文批注视图 · 接口契约与数据自洽测试（在服务器上用 python3 跑，纯 HTTP，只读）。

测什么：
  ① 新接口形状对不对（/annot、/page、/pageimg）
  ② **锚定数据端到端自洽**：标了「精确」的批注，把它的字符区间取回来必须真的等于摘录
     （只看服务端统计不算数 —— 中间隔着一层 HTTP 和一次 JSON 序列化）
  ③ 回归：既有接口（reports / review / download / 静态资源 / 独立页）没被改坏
"""
import json
import re
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"
fails, warns = [], []


def get(path, timeout=180):
    url = BASE + path
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:
        return 0, str(e).encode(), {}


def jget(path, timeout=180):
    st, body, _ = get(path, timeout)
    try:
        return st, json.loads(body.decode("utf-8"))
    except Exception:
        return st, None


def enc(s):
    return urllib.parse.quote(s)


def norm(s):
    return re.sub(r"[\s\u3000]+", "", s or "")


# ---------------------------------------------------------------- 0) 基础
st, body, _ = get("/health")
if st != 200:
    fails.append("/health 不是 200：%s" % st)
print("健康检查：", st)

st, rep = jget("/audit/api/reports")
if st != 200 or not rep or not rep.get("ok"):
    fails.append("/audit/api/reports 坏了：%s %s" % (st, str(rep)[:120]))
    print("报告清单拿不到，后续测试无法进行")
    sys.exit(1)
names = [r["name"] for r in rep["reports"]]
print("报告清单：%d 份" % len(names))

# ---------------------------------------------------------------- 1) 静态与页面
for p in ("/audit", "/audit/static/audit_ui.js", "/audit/static/audit_doc.js",
          "/audit/static/audit_ui.css", "/audit/static/audit_page.js"):
    st, body, _ = get(p)
    flag = "OK" if st == 200 and len(body) > 200 else "FAIL"
    if flag == "FAIL":
        fails.append("%s → %s (%d 字节)" % (p, st, len(body)))
    print("  %-34s %s %s %dB" % (p, st, flag, len(body)))
st, body, _ = get("/audit")
if b"auditRoot" not in body:
    fails.append("/audit 页面里没有 auditRoot 容器")
if b"audit_doc" not in body and b"audit_ui" not in body:
    fails.append("/audit 页面没有引用到审核界面模块")
# 白名单必须挡住目录穿越
st, _, _ = get("/audit/static/..%2f..%2fconfig.py")
if st == 200:
    fails.append("静态白名单可以穿越！")
print("  白名单穿越测试 → %s" % st)

# ---------------------------------------------------------------- 2) 逐份报告的批注
tot = {"精确": 0, "近似": 0, "仅页码": 0, "无证据": 0}
checked_exact = 0
checked_table = 0        # 走了"表格定位"这条路的批注有几条（0 就说明这条路没被真正测到）
done_names = []          # 有审核结果的报告（导出测试用第一份）
for name in names:
    st, d = jget("/audit/api/annot/" + enc(name) + "?parse=0")
    if st != 200 or not d:
        warns.append("%s：/annot 返回 %s（可能没有审核结果，属正常）" % (name, st))
        continue
    if not d.get("ok"):
        # 没有审核结果的报告会走到这里，不算失败
        print("  %-46s 跳过（%s）" % (name[:46], (d.get("message") or "")[:40]))
        continue
    pages = d.get("pages") or 0
    anchors = d.get("anchors") or []
    done_names.append(name)
    st2 = d.get("定位统计") or {}
    for k in tot:
        tot[k] += st2.get(k, 0)
    print("  %-46s %d 页 / %d 条批注 / 精确 %d 近似 %d 仅页码 %d 无证据 %d"
          % (name[:46], pages, len(anchors), st2.get("精确", 0), st2.get("近似", 0),
             st2.get("仅页码", 0), st2.get("无证据", 0)))
    if not anchors:
        fails.append("%s：批注为空" % name)
    for a in anchors:
        for k in ("item", "审核项", "结论", "level", "why"):
            if k not in a:
                fails.append("%s：批注缺字段 %s" % (name, k))
                break
        if a.get("level") not in ("精确", "近似", "仅页码", "无证据"):
            fails.append("%s：未知定位档位 %s" % (name, a.get("level")))
        if a.get("page") is not None and not (1 <= a["page"] <= pages):
            fails.append("%s：批注页码越界 P%s" % (name, a["page"]))
        if a.get("level") == "无证据" and (a.get("page") or a.get("quote")):
            fails.append("%s：无证据条目却带页码/摘录" % name)
        if a.get("level") == "精确" and not a.get("span"):
            fails.append("%s：精确档却没有字符区间" % name)

    # 取一条「精确」的批注，走 HTTP 把那一页要回来，逐字核对
    ex = [a for a in anchors if a.get("level") == "精确" and a.get("span")]
    if ex:
        a = ex[0]
        st3, pg = jget("/audit/api/page/%s?n=%d" % (enc(name), a["page"]))
        if st3 != 200 or not pg or not pg.get("ok"):
            fails.append("%s：取第 %s 页失败" % (name, a["page"]))
        else:
            s, e = a["span"]
            got = norm(pg["text"][s:e])
            want = norm(a["quote"])
            if got != want:
                fails.append("%s：「精确」档对不上 —— 取回「%s」≠ 摘录「%s」"
                             % (name, got[:40], want[:40]))
            else:
                checked_exact += 1
            if pg.get("n") != a["page"]:
                fails.append("%s：页号回显不对 %s≠%s" % (name, pg.get("n"), a["page"]))
    # 表格：有表格的页要能取到 rows
    tb = [a for a in anchors if a.get("table") is not None]
    if tb:
        a = tb[0]
        st4, pg = jget("/audit/api/page/%s?n=%d" % (enc(name), a["page"]))
        if st4 == 200 and pg and pg.get("ok"):
            if a["table"] >= len(pg.get("tables") or []):
                fails.append("%s：表格序号越界 %s" % (name, a["table"]))
            elif not (pg["tables"][a["table"]].get("rows")):
                fails.append("%s：表格没有 rows" % name)
            else:
                checked_table += 1
    # 扫描页渲染
    empt = d.get("empty_pages") or []
    if empt:
        st5, body, hdr = get("/audit/api/pageimg/%s?n=%d" % (enc(name), empt[0]))
        ok = st5 == 200 and body[:8] == b"\x89PNG\r\n\x1a\n"
        if not ok:
            fails.append("%s：扫描页渲染失败 %s" % (name, st5))
        else:
            print("      扫描页 P%s 渲染 OK（%d 字节）" % (empt[0], len(body)))

print()
print("批注合计：", tot, " 端到端逐字核对通过 %d 条" % checked_exact)
print("表格定位路径：实际校验 %d 条%s" % (checked_table, "" if checked_table else "（⚠️ 没测到）"))

# ---------------------------------------------------------------- 4) 交付件导出
# 走完整链路：HTTP 生成 → HTTP 下载 → 用库把产物打开核对。
# 只看"接口返回 ok"是不够的：文件可能是空的、页数可能不对、批注可能一个都没写进去。
print()
if done_names:
    import time
    nm = done_names[0]
    t0 = time.time()
    st, r = jget("/audit/api/export_pdf/" + enc(nm), timeout=1800)
    dt = time.time() - t0
    if st != 200 or not r or not r.get("ok"):
        fails.append("导出批注版 PDF 失败：%s %s" % (st, str(r)[:200]))
    else:
        print("批注版 PDF：%.0fs，批注 %s 条，%s 页 + 汇总 %s 页"
              % (dt, r.get("marks"), r.get("原页数"), r.get("汇总页")))
        if not str(r.get("file", "")).endswith(".批注版.pdf"):
            fails.append("批注版 PDF 文件名不对：%s" % r.get("file"))
        if not r.get("download"):
            fails.append("批注版 PDF 没有给下载地址")
        else:
            st2, body, hdr = get(r["download"], timeout=600)
            if st2 != 200 or not body.startswith(b"%PDF"):
                fails.append("下载批注版 PDF 失败：%s %s" % (st2, body[:20]))
            elif "pdf" not in (hdr.get("content-type") or ""):
                fails.append("批注版 PDF 的 media type 不对：%s" % hdr.get("content-type"))
            else:
                print("   下载 %.1f MB，media type %s" % (len(body) / 1048576, hdr.get("content-type")))
                import pymupdf
                tmp = "/tmp/_契约_批注版.pdf"
                open(tmp, "wb").write(body)
                doc = pymupdf.open(tmp)
                want = (r.get("原页数") or 0) + (r.get("汇总页") or 0)
                if doc.page_count != want:
                    fails.append("批注版页数不对：%d ≠ %s" % (doc.page_count, want))
                mine = sum(1 for i in range(doc.page_count)
                           for a in list(doc[i].annots() or [])
                           if (a.info.get("title") or "").startswith("AI审核·"))
                if mine != r.get("marks"):
                    fails.append("批注数不对：下载回来 %d ≠ 生成时 %s" % (mine, r.get("marks")))
                else:
                    print("   打开核对：%d 页，AI批注 %d 个 ✓" % (doc.page_count, mine))
                doc.close()

    t0 = time.time()
    st, r = jget("/audit/api/export_docx/" + enc(nm), timeout=900)
    n_docx = (r.get("条目") or 0) if isinstance(r, dict) else 0   # r 后面会被别的响应覆盖
    if st != 200 or not r or not r.get("ok"):
        fails.append("导出审核意见书失败：%s %s" % (st, str(r)[:200]))
    else:
        print("审核意见书：%.0fs，明细 %s 条" % (time.time() - t0, r.get("条目")))
        st2, body, hdr = get(r["download"], timeout=600)
        if st2 != 200 or not body.startswith(b"PK"):
            fails.append("下载意见书失败：%s %s" % (st2, body[:20]))
        elif "wordprocessingml" not in (hdr.get("content-type") or ""):
            fails.append("意见书 media type 不对：%s" % hdr.get("content-type"))
        else:
            from docx import Document
            tmp = "/tmp/_契约_意见书.docx"
            open(tmp, "wb").write(body)
            dd = Document(tmp)
            txt = "\n".join(p.text for p in dd.paragraphs)
            if "环境影响报告书审核意见书" not in txt:
                fails.append("意见书里没有封面标题")
            elif "审核单位（盖章）" not in txt:
                fails.append("意见书里没有落款栏")
            else:
                print("   打开核对：%d 段、%d 表，封面与落款都在 ✓"
                      % (len(dd.paragraphs), len(dd.tables)))

    # ------------------------------------------------ 4.5) 读回已有的审核结果
    # 2026-09-22 加：跑完审核会自动切到「原文批注」，但刷新一下 state.result 就没了，
    # 于是补了 /api/result 把磁盘上的结果读回来（否则用户得重跑几十分钟的审核）。
    st, rr = jget("/audit/api/result/" + enc(nm), timeout=120)
    if st != 200 or not rr or not rr.get("ok"):
        fails.append("读回审核结果失败：%s %s" % (st, str(rr)[:150]))
    elif not rr.get("has"):
        warns.append("这份报告没有落盘结果，跳过读回检查")
    else:
        items = ((rr.get("result") or {}).get("items") or [])
        st2, rep = jget("/audit/api/reports", timeout=120)
        marked = [x for x in ((rep or {}).get("reports") or []) if x.get("已审核")]
        print("读回结果：%d 条审核项，%s；清单里标了 %d 份『已审核』"
              % (len(items), rr.get("time") or "—", len(marked)))
        if len(items) != 18:
            fails.append("读回的结果审核项不是 18 条：%d" % len(items))
        if not any(x.get("name") == nm for x in marked):
            fails.append("清单里这份报告没标『已审核』")
        if st2 != 200 or not rep.get("ok"):
            fails.append("报告清单接口异常：%s" % st2)

    # ---------------------------------------------------------- 5) 网页内预览
    # 用户问「这个没办法在网页中预览吗」。PDF 走内联（浏览器自带阅读器），
    # 意见书走服务端渲染的网页预览版。这里把两条路都真的走一遍。
    st, r = jget("/audit/api/deliv/" + enc(nm), timeout=120)
    if st != 200 or not r or not r.get("ok"):
        fails.append("交付件状态接口失败：%s %s" % (st, str(r)[:150]))
    else:
        print("交付件状态：PDF %s / 意见书 %s"
              % ((r.get("pdf") or {}).get("time") or "未生成",
                 (r.get("docx") or {}).get("time") or "未生成"))
        if not r.get("pdf") or not r.get("docx"):
            fails.append("刚导出过，deliv 却说没生成")

    st, body, hdr = get("/audit/api/preview_pdf/" + enc(nm), timeout=1800)
    ct = (hdr.get("content-type") or "")
    if st != 200 or not body.startswith(b"%PDF"):
        fails.append("预览批注版 PDF 失败：%s %s" % (st, body[:20]))
    elif "pdf" not in ct:
        fails.append("预览批注版 PDF 的 media type 不对：%s" % ct)
    elif "inline" not in (hdr.get("content-disposition") or ""):
        # 关键：必须 inline。写成 attachment 浏览器就会弹下载框，
        # 那"网页内预览"就等于没做（而不是一个看得见的小毛病）。
        fails.append("批注版 PDF 不是内联返回：%s" % hdr.get("content-disposition"))
    else:
        print("预览批注版 PDF：200，%.1f MB，%s，Content-Disposition: inline ✓"
              % (len(body) / 1048576, ct))

    st, body, hdr = get("/audit/api/preview_docx/" + enc(nm), timeout=600)
    txt = body.decode("utf-8", "replace") if isinstance(body, bytes) else str(body)
    if st != 200:
        fails.append("预览意见书失败：%s" % st)
    elif "text/html" not in (hdr.get("content-type") or ""):
        fails.append("意见书预览不是 HTML：%s" % hdr.get("content-type"))
    elif "环境影响报告书审核意见书" not in txt:
        fails.append("意见书预览里没有封面标题")
    elif "审核单位（盖章）" not in txt:
        fails.append("意见书预览里没有落款栏")
    elif "window.print()" not in txt:
        fails.append("意见书预览里没有打印入口")
    else:
        print("预览意见书（网页版）：200，%d KB，含封面/落款/打印入口 ✓" % (len(body) // 1024))
        # 结构检查：没有无头浏览器，看不到排版，但 DOM 结构与"表格行列对齐"能查
        # （行列不齐在浏览器里就是错位的表格，光看文本看不出来）。
        # 用 XPath 而不是 cssselect：服务器 venv 里没装 cssselect 包。
        import lxml.html as LH

        def by_class(name):
            return '//*[contains(concat(" ", normalize-space(@class), " "), " %s ")]' % name

        hd = LH.fromstring(txt)
        bad = []
        for ti, tb in enumerate(hd.xpath('//table'), 1):
            rows = tb.xpath('.//tr')
            if not rows:
                bad.append("表%d 没有行" % ti)
                continue
            n = len(rows[0].xpath('./th|./td'))
            for ri, tr in enumerate(rows, 1):
                real = len(tr.xpath('./th|./td'))
                if real != n:
                    bad.append("表%d 第%d行 %d 列 ≠ 表头 %d 列" % (ti, ri, real, n))
        sign = hd.xpath(by_class("sign"))
        lis = hd.xpath(by_class("li"))
        if bad:
            fails.append("意见书网页版表格结构有问题：%s" % bad[:3])
        else:
            print("   结构核对：%d 个表行列对齐 ✓，%d 个小节标题、%d 条落款行、%d 条档位说明"
                  % (len(hd.xpath('//table')), len(hd.xpath('//h2')), len(sign), len(lis)))
        if len(hd.xpath('//h1')) != 1:
            fails.append("意见书网页版没有唯一的封面标题")
        if len(sign) != 4:
            fails.append("意见书网页版落款行不是 4 条：%d" % len(sign))
        if len(lis) != 4:
            fails.append("意见书网页版档位说明不是 4 条：%d" % len(lis))
        # 版面宽度：A4 宽 21cm − 左右各 20mm 内边距 = 17cm。
        # 列宽合计超了，浏览器里就是表格撑出纸面（和 PDF 那边"文字顶出页边"同一类毛病）。
        for ti, cg in enumerate(hd.xpath('//colgroup'), 1):
            total = 0.0
            for c in cg.xpath('./col'):
                m = re.match(r'^([\d.]+)cm$', (c.get('style') or '').split(':')[-1].strip())
                if m:
                    total += float(m.group(1))
            if total > 17.0:
                fails.append("意见书网页版第 %d 个表列宽合计 %.1fcm > 17cm" % (ti, total))
        print("   版面宽度：%d 个表的列宽合计都不超过 17cm ✓" % len(hd.xpath('//colgroup')))
        # 明细条数与 docx 一致（两个渲染器同源，条数不一致说明其中一路漏了内容）
        n_review = len(hd.xpath(by_class("review")))
        if n_review != n_docx:
            fails.append("意见书网页版明细 %d 条 ≠ docx %d 条" % (n_review, n_docx))
        else:
            print("   与 docx 同源核对：明细均为 %d 条 ✓" % n_review)
else:
    warns.append("没有任何报告有审核结果，跳过导出测试")

# ---------------------------------------------------------------- 3) 回归
st, rev = jget("/audit/api/review/" + enc(names[0]))
if st != 200 or rev is None:
    fails.append("人工复核接口坏了：%s" % st)
else:
    print("人工复核接口：", st, "ok=", rev.get("ok"))
st, body, hdr = get("/audit/api/download/1%E3%80%81%E7%8E%AF%E8%AF%84%E6%8A%A5%E5%91%8A.%E5%AE%A1%E6%A0%B8%E8%A1%A8.csv")
print("下载既有 CSV：", st, hdr.get("content-type"), len(body), "字节")
if st == 200 and "csv" not in (hdr.get("content-type") or ""):
    fails.append("CSV 的 media type 不对：%s" % hdr.get("content-type"))

# ---------------------------------------------------------------- 结论
print()
if fails:
    print("❌ 失败 %d 条：" % len(fails))
    for f in fails:
        print("   -", f)
if warns:
    print("⚠️  提示 %d 条：" % len(warns))
    for w in warns:
        print("   -", w)
if not fails:
    print("✅ 全部通过")
sys.exit(1 if fails else 0)
