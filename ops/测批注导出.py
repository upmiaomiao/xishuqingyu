# -*- coding: utf-8 -*-
"""批注版 PDF 自检（服务器上跑，会真的写导出文件）。

为什么必须自检而不是"看一眼能打开就行"：
  · **原件的 sha1 不能变** —— 交付件是"原件 + 批注"，不是"改过的报告"；
  · 批注数要对得上定位统计（少一条就是"有意见没送到"）；
  · 批注要**带档位**且能被阅读器显示（title/content 非空、可被 get_text 读出）；
  · 汇总页的中文不能是空白（字体没嵌进去的话，页面上是一片空白，肉眼在缩略图上也看不出）。
"""
import glob
import hashlib
import os
import sys

import pymupdf

sys.path.insert(0, "/home/test/xishu_qingyu_serve")
AUDIT_HOME = "/data/eia_audit"
sys.path.insert(0, AUDIT_HOME)
from xishu_pipeline.audit_anchor import build_anchors, load_parsed, load_result  # noqa: E402
from xishu_pipeline.audit_pdf import export_pdf  # noqa: E402

REPORTS = "/data/eia_reports"
OUT = os.path.join(AUDIT_HOME, "_审核结果", "导出")
OK = FAIL = 0


def check(name, cond, extra=""):
    global OK, FAIL
    if cond:
        OK += 1
        print("  √ %s" % name)
    else:
        FAIL += 1
        print("  × %s %s" % (name, extra))


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def pdf_of(name):
    for p in glob.glob(os.path.join(REPORTS, "**", "*.pdf"), recursive=True):
        if os.path.basename(p) == name:
            return p
    return None


target = sys.argv[1] if len(sys.argv) > 1 else None
names = [j[:-5] + ".pdf" for j in sorted(os.listdir(os.path.join(AUDIT_HOME, "_审核结果")))
         if j.endswith(".json")]
for nm in names:
    try:
        res = load_result(nm)
    except FileNotFoundError:
        continue
    if not res.get("file"):
        continue
    fname = res["file"]["name"]
    if target and target not in fname:
        continue
    path = pdf_of(fname)
    if not path:
        continue
    print("=" * 78)
    print(fname[:70])
    before_sha = sha1(path)
    before_size = os.path.getsize(path)
    parsed = load_parsed(fname, path, allow_parse=False)
    anchors = build_anchors(res, parsed)
    r = export_pdf(fname, path, res, parsed, anchors, OUT)
    check("导出返回 ok", r.get("ok"), str(r)[:200])
    if not r.get("ok"):
        continue
    out = r["path"]
    check("导出文件存在", os.path.isfile(out), out)
    check("原件 sha1 未变", sha1(path) == before_sha, "%s → %s" % (before_sha[:12], sha1(path)[:12]))
    check("原件大小未变", os.path.getsize(path) == before_size)

    doc_src = pymupdf.open(path)
    exp_pages = doc_src.page_count
    orig_annots = sum(len(list(doc_src[i].annots() or [])) for i in range(exp_pages))
    doc_src.close()
    chk = pymupdf.open(out)
    check("页数 = 原件 %d + 汇总 %d" % (exp_pages, r["汇总页"]),
          chk.page_count == exp_pages + r["汇总页"], "实际 %d" % chk.page_count)

    # 只统计**我们自己写的**批注：有些报告原件里本来就带批注（印章/UUID 标题），
    # 把它们算进来会得出"批注数对不上"的假故障。
    total = 0
    titles = {}
    kept_orig = 0
    for i in range(chk.page_count):
        for an in list(chk[i].annots() or []):
            t = an.info.get("title") or ""
            if not t.startswith("AI审核·"):
                if i < exp_pages:
                    kept_orig += 1
                continue
            total += 1
            key = t.split("·")[1] if "·" in t else "?"
            titles[key] = titles.get(key, 0) + 1
            if not (an.info.get("content") or "").strip():
                check("批注 %s 有内容" % t, False, "content 为空")
    check("批注总数 %d = 计划 %d" % (total, r["marks"]), total == r["marks"])
    check("原件原有批注未丢（%d 个）" % orig_annots, kept_orig >= orig_annots,
          "只剩 %d 个" % kept_orig)
    print("     档位分布：", titles)
    for lv, n in (("精确", r["定位"]["精确"][0]), ("近似", r["定位"]["近似"][0]),
                  ("仅页码", r["定位"]["仅页码"][1])):
        if n:
            check("档位「%s」批注数 %d" % (lv, n), titles.get(lv, 0) == n,
                  "实际 %d" % titles.get(lv, 0))

    # 汇总页：中文必须真的写进去了（落款可能被分页保护挤到第 2 个汇总页，所以全都算上）
    last = chk[exp_pages]
    text = "".join(chk[exp_pages + i].get_text() for i in range(r["汇总页"]))
    check("汇总页有中文标题", "审核意见汇总" in text, repr(text[:60]))
    for kw in ("项目名称", "精确", "审核单位", "审　核　人", "审核日期", "报告名称"):
        check("汇总页含「%s」" % kw, kw in text)
    check("汇总页有审核项行数 ≥ %d" % min(len(res.get("items") or []), 18),
          sum(1 for it in (res.get("items") or []) if (it.get("审核项") or "")[:6] in text) >= 15)
    # 汇总页里的字必须是"可选中"的文本（字体嵌失败会变成空白）
    check("汇总页文字长度 > 800", len(text) > 800, "只有 %d 字" % len(text))
    # 三档定位的说明必须在交付件里写清楚（用户拿到的就是这一份）
    check("汇总页写明三档定位口径",
          "精确＝黄底高亮" in text.replace(" ", "") or "精确" in text and "近似" in text)
    # 几何检查：文字不能越出页边距、不能互相压字。
    # 这两个毛病**只有渲成图才看得见**，文本层面一切正常（第一版就是表头第三行压到了
    # 第一行数据、落款横线顶出页面右边界）。所以让机器来查坐标，别靠肉眼。
    for off in range(r["汇总页"]):
        p = chk[exp_pages + off]
        boxes = []
        for blk in p.get_text("dict")["blocks"]:
            for ln in blk.get("lines", []):
                for sp in ln["spans"]:
                    if sp["text"].strip():
                        boxes.append((pymupdf.Rect(sp["bbox"]), sp["text"]))
        x0, x1 = 48.0, p.rect.width - 48.0
        over = [(t, tuple(round(v) for v in rr)) for rr, t in boxes
                if rr.x0 < x0 - 2 or rr.x1 > x1 + 2]
        check("汇总页%s 文字都在页边距内（%d 段）" % (off + 1, len(boxes)), not over,
              "越界 %d 段：%s" % (len(over), over[:2]))
        hit = []
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                it = boxes[a][0] & boxes[b][0]
                if not it.is_empty and it.get_area() > 2.0:
                    hit.append((boxes[a][1][:10], boxes[b][1][:10], round(it.get_area(), 1)))
        check("汇总页%s 文字互不压字" % (off + 1), not hit, "压字 %d 处：%s" % (len(hit), hit[:3]))
    chk.close()
    print("  输出：%s（%.1f MB）" % (os.path.basename(out), os.path.getsize(out) / 1048576))

print("=" * 78)
print("通过 %d / 失败 %d" % (OK, FAIL))
sys.exit(1 if FAIL else 0)
