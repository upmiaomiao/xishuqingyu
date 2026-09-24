# -*- coding: utf-8 -*-
"""审核意见书：一份内容，两种渲染（.docx 交付件 + 网页预览版）。

和批注版 PDF 的分工（用户 2026-09-22 拍板）：
  · 批注版 PDF = 在报告原文上"哪里有问题"，主交付件；
  · 意见书     = "有哪些问题、依据是什么、谁签的字"，一页页能打印、能盖章。

为什么有"网页预览版"（2026-09-22 追加）：docx 浏览器**不能原生渲染**，
服务器上也没有 LibreOffice / pandoc / 无头浏览器（`探预览能力.sh` 实测），
转不成 PDF。所以意见书的内容抽成 `build_blocks()` 这一份数据，
docx 与 HTML 两个渲染器都从它走 —— 否则两处结构必然走样
（"改了 docx 忘了改预览"这类问题，肉眼很难发现）。

排版约定：正文宋体五号（10.5pt），表格九号；A4、页边距 2.5cm。
python-docx 默认字体是西文（Calibri），中文要显式设 `w:eastAsia`，
否则在 Word 里会退化成默认中文字体。
"""
from __future__ import annotations

import html
import os
from datetime import datetime

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .audit_anchor import LEVEL_EXACT, LEVEL_NEAR, LEVEL_PAGE, LEVEL_NONE, RESULT_DIR

# 分级：必须整改 → 需核实 → 优化建议（无问题/不适用只在附表里列一行）
SECTIONS = [
    ("存在问题", "一、必须整改的问题", "以下问题须在报批前修改到位。"),
    ("存在疑似问题", "二、需核实的问题", "以下事项 AI 判定依据不足或存在歧义，须人工核实后确定。"),
    ("优化调整建议", "三、优化调整建议", "以下为完善性建议，不影响结论成立。"),
]
SEV_FONT = "宋体"
STATE_NOTE = {"存在问题": "必须整改", "存在疑似问题": "需人工核实",
              "优化调整建议": "完善性建议", "无问题": "未发现问题",
              "不适用": "本项目不涉及"}
LEVEL_DESC = (
    (LEVEL_EXACT, "摘录与报告原文逐字一致，在批注版 PDF 中为黄底高亮。"),
    (LEVEL_NEAR, "按关键词或表格内容定位，可能有偏移，在批注版 PDF 中为蓝色下划线/蓝框，请以原文为准。"),
    (LEVEL_PAGE, "只能在给出的页码上人工核对，批注版 PDF 中以页边批注标注，正文不作高亮。"),
    (LEVEL_NONE, "该审核项未给出证据（多为不适用项），不代表「没有问题」。"),
)
SIGN_LINES = ("审核单位（盖章）：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿",
              "审　核　人：＿＿＿＿＿＿＿＿　　（签字）",
              "审核日期：＿＿＿＿年＿＿＿月＿＿＿日",
              "报告名称：＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿")


# ================================================================ 内容（唯一来源）

def _by_item(anchors: list) -> dict:
    """批注 → 按审核项归并（一个审核项可能有多条证据）。"""
    out: dict = {}
    for a in anchors:
        out.setdefault(a.get("审核项") or "", []).append(a)
    return out


def _ev_line(a: dict) -> str:
    pg = "物理页 P%s" % a["page"] if a.get("page") else "无页码"
    if a.get("printed"):
        pg += "（印刷页 %s）" % a["printed"]
    lv = a.get("level") or ""
    if lv == LEVEL_NONE:
        return "证据：无（该审核项未给出证据）"
    return "证据（%s）：%s　%s" % (lv, pg, (a.get("quote") or "")[:300])


def _pgs_of(anchors: list) -> str:
    return "、".join(
        ("%s%s" % (a["page"], "(%s)" % a["printed"] if a.get("printed") else ""))
        for a in anchors if a.get("page")) or "—"


def build_blocks(name: str, result: dict, anchors: list, review: dict = None):
    """把审核结果摊成"意见书内容块"，docx 与网页版共用。返回 (blocks, meta)。"""
    review = review or {}
    f = result.get("file") or {}
    st = result.get("统计") or {}
    items = result.get("items") or []
    by_item = _by_item(anchors)
    rp = os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json")
    try:
        done_at = datetime.fromtimestamp(os.path.getmtime(rp)).strftime("%Y-%m-%d %H:%M")
    except OSError:
        done_at = "—"

    B: list = []
    B.append({"k": "h1", "t": "环境影响报告书审核意见书"})
    B.append({"k": "kv", "rows": [
        ("项目名称", f.get("项目名称") or "（未识别）"),
        ("报告文件", f.get("name") or name),
        ("文件类型", f.get("环评文件类型") or "—"),
        ("报告页数", "%s 页" % (f.get("pages") or "—")),
        ("审核方式", "AI 辅助审核（18 项固定审核项）＋ 人工复核"),
        ("审核完成时间", done_at),
        ("出具时间", datetime.now().strftime("%Y-%m-%d %H:%M")),
    ]})
    B.append({"k": "h2", "t": "审核结论统计"})
    B.append({"k": "grid", "cls": "stat",
              "head": ["结论", "项数", "说明"],
              "rows": [[k, st.get(k, 0), STATE_NOTE.get(k, "")]
                       for k in ("存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用")],
              "w": [3.4, 1.8, 10.8], "size": 9.5})
    B.append({"k": "p", "size": 9, "t":
              "说明：本意见书由审核系统自动生成，逐条给出参考依据、判定理由与证据出处；"
              "带「需人工确认」标记的条目必须由审核人复核后方可出具。"})
    # 「不适用」口径 —— 2026-09-22 用户反馈（看到 9 条"不适用"不知道是不是漏审）。
    # 实测：报告书的 38 条"不适用"全是同一个原因，写清楚比让人猜好。
    if st.get("不适用"):
        _kind = str(f.get("环评文件类型") or "")
        if "报告书" in _kind:
            _na = ("关于「不适用」：本报告为%s，其中「专项评价设置」类 9 项是《建设项目环境影响"
                   "报告表编制技术指南（污染影响类）》表1 的判据，报告书不受该指南约束，"
                   "故判「不适用」——不是漏审，也不是没查到；相应条目仍列在附表里备查。" % _kind)
        else:
            _na = ("关于「不适用」：这些项是按相应判据设置的，本报告不涉及该判据适用的情形，"
                   "故判「不适用」——不是漏审，也不是没查到；相应条目仍列在附表里备查。")
        B.append({"k": "p", "size": 9, "t": _na})
    B.append({"k": "brk"})

    n_detail = 0
    for state, title, lead in SECTIONS:
        rows = [(no, it) for no, it in enumerate(items, 1) if (it.get("AI审核") or "") == state]
        if not rows:
            continue
        B.append({"k": "h2", "t": title})
        B.append({"k": "p", "size": 10, "t": lead})
        for no, it in rows:
            k = it.get("审核项") or ""
            rv = review.get(k) or {}
            B.append({"k": "h3", "t": "第 %d 条　%s" % (no, k)})
            B.append({"k": "kv", "rows": [
                ("类别", it.get("类别") or "—"),
                ("AI 结论", "%s（置信度 %s）" % (state, it.get("置信度") or "—")),
                ("参考依据", it.get("参考依据") or "—"),
                ("判定理由", it.get("理由") or "—"),
                ("环评文件出处", it.get("环评文件") or "—"),
                ("需人工确认", "；".join(it.get("需人工确认") or []) or "无"),
            ]})
            for a in (by_item.get(k) or []):
                B.append({"k": "ev", "t": _ev_line(a)})
                if a.get("why"):
                    B.append({"k": "ev", "t": "定位说明：%s" % a["why"]})
            B.append({"k": "grid", "cls": "review",
                      "head": ["人工复核结论", "复核意见", "复核人 / 日期"],
                      "rows": [[rv.get("人工修改") or "　", rv.get("备注") or "　", "　"]],
                      "w": [3.6, 8.4, 4.0], "size": 8.5})
            n_detail += 1

    rest = [it for it in items if (it.get("AI审核") or "") in ("无问题", "不适用")]
    if rest:
        B.append({"k": "h2", "t": "附表　未发现问题与不适用项"})
        B.append({"k": "p", "size": 9, "t": "「无问题」的结论同样有原文依据，页码列在这里备查。"})
        B.append({"k": "grid", "cls": "rest",
                  "head": ["序号", "审核项", "结论", "证据页（物理/印刷）", "说明"],
                  "rows": [[i, it.get("审核项"), it.get("AI审核"),
                            _pgs_of(by_item.get(it.get("审核项")) or []),
                            (it.get("理由") or "")[:70]] for i, it in enumerate(rest, 1)],
                  "w": [1.1, 4.0, 2.1, 3.0, 5.8], "size": 8.5})

    B.append({"k": "h2", "t": "附注　证据定位档位说明"})
    B.append({"k": "p", "size": 9.5, "t": "本意见书每一条证据都标注了定位档位，含义如下："})
    for lv, desc in LEVEL_DESC:
        B.append({"k": "li", "t": "· %s：%s" % (lv, desc)})

    B.append({"k": "gap", "h": 14})
    B.append({"k": "p", "size": 11,
              "t": "审核结论（人工）：□ 同意出具　□ 修改后出具　□ 需重新审核"})
    for line in SIGN_LINES:
        B.append({"k": "sign", "t": line})
    meta = {"条目": n_detail, "页数": f.get("pages"), "统计": st}
    return B, meta


# ================================================================ 渲染①：docx

def _setup(doc: Document):
    """A4 + 中文正文字体（西文与 eastAsia 都要设）。"""
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
    sec.left_margin = sec.right_margin = Cm(2.5)
    sec.top_margin = sec.bottom_margin = Cm(2.5)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(10.5)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), SEV_FONT)


def _p(doc, text="", size=10.5, bold=False, align=None, space_after=4, indent=None):
    p = doc.add_paragraph()
    if align is not None:
        p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    if indent:
        p.paragraph_format.left_indent = Cm(indent)
    r = p.add_run(text)
    r.font.size = Pt(size)
    r.bold = bold
    r.font.name = "Times New Roman"
    r._element.rPr.rFonts.set(qn("w:eastAsia"), SEV_FONT)
    return p


def _kv_table(doc, rows, widths=(3.4, 12.6), size=10):
    t = doc.add_table(rows=0, cols=2)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for k, v in rows:
        c = t.add_row().cells
        for cell, txt, wd in ((c[0], k, widths[0]), (c[1], v, widths[1])):
            cell.width = Cm(wd)
            para = cell.paragraphs[0]
            para.paragraph_format.space_after = Pt(1)
            r = para.add_run(str(txt))
            r.font.size = Pt(size)
            r.font.name = "Times New Roman"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), SEV_FONT)
    return t


def _grid(doc, header, rows, widths, size=8.5):
    t = doc.add_table(rows=1, cols=len(header))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(header):
        cell = t.rows[0].cells[i]
        cell.width = Cm(widths[i])
        r = cell.paragraphs[0].add_run(h)
        r.bold = True
        r.font.size = Pt(size)
        r.font.name = "Times New Roman"
        r._element.rPr.rFonts.set(qn("w:eastAsia"), SEV_FONT)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].width = Cm(widths[i])
            para = cells[i].paragraphs[0]
            para.paragraph_format.space_after = Pt(1)
            r = para.add_run(str(v))
            r.font.size = Pt(size)
            r.font.name = "Times New Roman"
            r._element.rPr.rFonts.set(qn("w:eastAsia"), SEV_FONT)
    return t


def _docx_block(doc, b):
    k = b["k"]
    if k == "h1":
        _p(doc, b["t"], 20, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=22)
    elif k == "h2":
        _p(doc, b["t"], 13.5, bold=True, space_after=6)
    elif k == "h3":
        _p(doc, b["t"], 11.5, bold=True, space_after=3)
    elif k == "p":
        _p(doc, b["t"], b.get("size", 10.5), space_after=4)
    elif k == "li":
        _p(doc, b["t"], b.get("size", 9.5), indent=0.4, space_after=2)
    elif k == "ev":
        _p(doc, b["t"], 9, indent=0.4, space_after=2)
    elif k == "sign":
        _p(doc, b["t"], 11, space_after=14)
    elif k == "gap":
        _p(doc, "", 10, space_after=b.get("h", 10))
    elif k == "kv":
        _kv_table(doc, b["rows"])
        _p(doc, "", 8, space_after=6)
    elif k == "grid":
        _grid(doc, b["head"], b["rows"], b["w"], b.get("size", 8.5))
        _p(doc, "", 6, space_after=8)
    elif k == "brk":
        doc.add_page_break()


def export_docx(name: str, result: dict, anchors: list, out_dir: str,
                review: dict = None) -> dict:
    """生成审核意见书 .docx。"""
    blocks, meta = build_blocks(name, result, anchors, review)
    doc = Document()
    _setup(doc)
    for b in blocks:
        _docx_block(doc, b)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, name.rsplit(".", 1)[0] + ".审核意见书.docx")
    doc.save(path)
    return {"ok": True, "file": os.path.basename(path), "path": path, **meta}


# ================================================================ 渲染②：网页预览

CSS = """
:root { color-scheme: light; }
body { margin: 0; padding: 18px 10px 40px; background: #eef1f5;
  font: 10.5pt/1.7 "Songti SC", SimSun, "Noto Serif CJK SC", serif; color: #16181d; }
.page { width: 21cm; max-width: 100%; margin: 0 auto; background: #fff; padding: 22mm 20mm;
  box-sizing: border-box; box-shadow: 0 2px 14px rgba(0,0,0,.12); }
h1 { font-size: 20pt; text-align: center; margin: 0 0 22px; letter-spacing: 2px; }
h2 { font-size: 13.5pt; margin: 20px 0 6px; border-left: 4px solid #2f6fd0; padding-left: 8px; }
h3 { font-size: 11.5pt; margin: 16px 0 4px; }
p { margin: 0 0 4px; }
.ev { font-size: 9pt; color: #3b4048; margin: 0 0 3px 14px; }
.li { font-size: 9.5pt; margin: 0 0 2px 14px; }
.sign { font-size: 11pt; margin: 16px 0 0; }
table { border-collapse: collapse; width: 100%; margin: 6px 0 10px; }
th, td { border: 1px solid #6b7280; padding: 3px 5px; font-size: 9pt;
  vertical-align: top; text-align: left; }
th { background: #f1f4f8; font-weight: 700; }
table.stat td:first-child, table.rest td:first-child { width: 3.4cm; }
table.rest td:nth-child(1) { width: 1.1cm; text-align: center; }
table.review td { height: 1.6em; }
.brk { page-break-after: always; height: 0; }
.bar { width: 21cm; max-width: 100%; margin: 0 auto 10px; display: flex; gap: 10px;
  align-items: center; font: 12px/1.6 system-ui, "Microsoft YaHei", sans-serif; color: #444; }
.bar b { font-size: 13px; color: #16181d; }
.bar .sp { flex: 1; }
.bar button { font: inherit; padding: 4px 12px; border: 1px solid #c3cad4; background: #fff;
  border-radius: 5px; cursor: pointer; }
.bar button:hover { border-color: #2f6fd0; color: #2f6fd0; }
@media print {
  body { background: #fff; padding: 0; }
  .page { width: auto; box-shadow: none; padding: 0; }
  .bar { display: none; }
  @page { size: A4; margin: 12mm; }
}
"""


def render_html(name: str, result: dict, anchors: list, review: dict = None) -> str:
    """把意见书渲染成网页预览版（可在浏览器里直接看、直接打印成 PDF）。"""
    blocks, meta = build_blocks(name, result, anchors, review)
    e = html.escape
    out = []
    for b in blocks:
        k = b["k"]
        if k in ("h1", "h2", "h3", "p", "li", "ev", "sign"):
            cls = {"p": "", "li": "li", "ev": "ev", "sign": "sign"}.get(k, "")
            tag = {"h1": "h1", "h2": "h2", "h3": "h3"}.get(k, "p")
            out.append('<%s%s>%s</%s>' % (tag, ' class="%s"' % cls if cls else "", e(b["t"]), tag))
        elif k == "gap":
            out.append('<div style="height:%dpx"></div>' % b.get("h", 10))
        elif k == "kv":
            rows = "".join("<tr><th style='width:3.4cm'>%s</th><td>%s</td></tr>"
                           % (e(str(a)), e(str(c))) for a, c in b["rows"])
            out.append("<table>%s</table>" % rows)
        elif k == "grid":
            head = "".join("<th>%s</th>" % e(str(h)) for h in b["head"])
            cols = "".join("<col style='width:%scm'>" % w for w in b["w"])
            rows = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % e(str(c)) for c in row)
                           for row in b["rows"])
            out.append('<table class="%s"><colgroup>%s</colgroup>'
                       "<thead><tr>%s</tr></thead><tbody>%s</tbody></table>"
                       % (b.get("cls", ""), cols, head, rows))
        elif k == "brk":
            out.append('<div class="brk"></div>')
    title = "%s · 审核意见书" % (result.get("file", {}).get("项目名称") or name)
    return ("<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\">"
            "<title>%s</title><style>%s</style></head><body>"
            "<div class=\"bar\"><b>审核意见书（网页预览版）</b>"
            "<span class=\"sp\"></span>"
            "<button onclick=\"window.print()\">打印 / 另存为 PDF</button>"
            "</div><div class=\"page\">%s</div></body></html>"
            % (e(title), CSS, "".join(out)))
