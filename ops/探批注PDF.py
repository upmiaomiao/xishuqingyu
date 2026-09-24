# -*- coding: utf-8 -*-
"""只读探针：批注版 PDF 的可行性（在服务器上用 venv python 跑）。

必须**先探再写**，因为这三点都可能有坑：
  ① `page.search_for(中文摘录)` 在这批报告上命中率多少 —— 决定"精确档"能不能真的画出高亮；
  ② 内置中文字体（china-s）能不能用、`text_length` 量得准不准 —— 决定汇总页能不能排版；
  ③ 写批注 + 新增页之后，原页数与批注数是不是预期。
输出只写到 /tmp，不动任何报告原件。
"""
import glob
import json
import os
import re
import sys

import pymupdf

REPORTS = "/data/eia_reports"
RESULTS = "/data/eia_audit/_审核结果"
print("pymupdf", pymupdf.__doc__.strip().splitlines()[0] if pymupdf.__doc__ else "?")


def result_of(name):
    stem = re.sub(r"\.[^.]+$", "", name)
    p = os.path.join(RESULTS, stem + ".json")
    return json.load(open(p, encoding="utf-8")) if os.path.isfile(p) else None


def pdf_of(name):
    for p in glob.glob(os.path.join(REPORTS, "**", "*.pdf"), recursive=True):
        if os.path.basename(p) == name:
            return p
    return None


def norm(s):
    return re.sub(r"[\s\u3000]+", "", s or "")


# ---------------------------------------------------------------- ①②
print("\n=== ① search_for 中文命中率 / ② 内置中文字体 ===")
tot = hit = 0
samples = []
for name in sorted(os.listdir(RESULTS)):
    if not name.endswith(".json"):
        continue
    r = result_of(name)
    if not r or "items" not in r:
        continue
    fname = r["file"]["name"]
    path = pdf_of(fname)
    if not path:
        continue
    doc = pymupdf.open(path)
    n = 0
    for it in r["items"]:
        for ev in it.get("证据") or []:
            q = ev.get("quote") or ""
            pg = ev.get("page")
            if len(q) < 8 or not pg:
                continue
            n += 1
            tot += 1
            page = doc[pg - 1]
            rects = page.search_for(q)
            how = "整条"
            if not rects:
                # 退一步：取最长的一段连续中文（≥8 字）再搜
                for seg in sorted(re.findall(r"[\u4e00-\u9fff，。；：、（）0-9%.]{8,}", q),
                                  key=len, reverse=True)[:3]:
                    rects = page.search_for(seg)
                    if rects:
                        how = "片段:" + seg[:14]
                        break
            if not rects:
                # 再退：取前 10 个非空白字符
                seg = norm(q)[:10]
                rects = page.search_for(seg) if len(seg) >= 6 else []
                how = "前缀:" + seg
            if rects:
                hit += 1
                if len(samples) < 3:
                    samples.append((fname[:18], pg, how, tuple(round(v, 1) for v in rects[0])))
    doc.close()
    print("  %-40s 证据 %d 条" % (fname[:40], n))
print("  合计 %d 条，search_for 命中 %d 条（%.0f%%）" % (tot, hit, 100.0 * hit / max(tot, 1)))
for s in samples:
    print("   样例：", s)

print("\n  内置中文字体：")
for fn in ("china-s", "china-ss", "cjk"):
    try:
        f = pymupdf.Font(fn)
        w = f.text_length("环境影响报告书审核意见", fontsize=10)
        print("   %-9s ok  名字=%s  10pt 下 12 个汉字的宽度 %.1fpt" % (fn, f.name, w))
    except Exception as exc:
        print("   %-9s 失败：%s" % (fn, exc))

# ---------------------------------------------------------------- ③
print("\n=== ③ 写批注 + 新增页 + 汇总页排版 ===")
name = next((n for n in sorted(os.listdir(RESULTS))
             if n.endswith(".json") and "临沂" in open(os.path.join(RESULTS, n), encoding="utf-8").read()[:2000]), None)
r = result_of(name)
path = pdf_of(r["file"]["name"])
doc = pymupdf.open(path)
before = doc.page_count
page = doc[0]
target = None
for it in r["items"]:
    for ev in it.get("证据") or []:
        if ev.get("quote") and ev.get("page"):
            h = doc[ev["page"] - 1].search_for(ev["quote"])
            if h:
                target = (ev["page"], ev["quote"], h)
                break
    if target:
        break
pg = doc[target[0] - 1]
a = pg.add_highlight_annot(target[2])
a.set_info(title="AI审核·精确", content="第 1 条 测试\n结论：存在问题\n定位：精确（与原文逐字一致）")
a.set_colors(stroke=(1, 0.85, 0.2))
a.update()
b = pg.add_text_annot(pymupdf.Point(pg.rect.width - 24, 24), "仅页码档的批注落在这里")
b.set_info(title="AI审核·仅页码", content="第 2 条 测试")
b.update()
c = pg.add_underline_annot(pg.search_for("环境影响")[:1]) if pg.search_for("环境影响") else None
if c:
    c.set_info(title="AI审核·近似", content="近似档用下划线")
    c.update()

# 新增汇总页（含中文、表格线、落款栏）
newp = doc.new_page(width=595, height=842)
font = pymupdf.Font("china-s")
y = 60
def line(txt, size=10, x=50, gap=None):
    global y
    newp.insert_text((x, y), txt, fontname="china-s", fontsize=size)
    y += gap if gap is not None else size * 1.7

line("审核意见汇总", 16)
line("项目名称：中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目", 10)
line("环评文件：环境影响报告书　　页数：%d　　审核时间：2026-09-22" % before, 10)
y += 6
newp.draw_line((50, y), (545, y), width=0.8)
y += 14
line("序号　审核项　　　　　　结论　　　证据页码", 9)
y += 2
newp.draw_line((50, y), (545, y), width=0.5)
y += 12
for i, it in enumerate(r["items"][:4], 1):
    ev = (it.get("证据") or [{}])[0]
    line("%d　%s　%s　物理P%s/印刷%s" % (i, it["审核项"][:12], it["AI审核"], ev.get("page"), ev.get("mark") or "-"), 9)
y += 20
line("审核单位：____________　审核人：__________", 10)
line("审核日期：____________　报告名称：______________________", 10)
out = "/tmp/_批注版试排.pdf"
doc.save(out, garbage=3, deflate=True)
doc.close()

chk = pymupdf.open(out)
print("  原 %d 页 → 输出 %d 页（+%d）" % (before, chk.page_count, chk.page_count - before))
print("  第 %d 页批注：%d 个 → %s" % (target[0], len(chk[target[0] - 1].annots() or []),
      [(x.type[1], x.info.get("title")) for x in (chk[target[0] - 1].annots() or [])]))
print("  汇总页文字前 60 字：", repr(chk[before].get_text()[:60]))
print("  文件大小 %.0f KB" % (os.path.getsize(out) / 1024))
chk.close()
print("\n（原件未改动：", path, os.path.getsize(path) // 1024, "KB）")
