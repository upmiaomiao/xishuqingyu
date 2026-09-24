# -*- coding: utf-8 -*-
"""把生成的 .docx 渲染成网页，用于"预览整份报告"。

为什么从 docx 反渲染、而不是另写一套 HTML 渲染：
  另写一套就等于**两份实现**，迟早不一致（用户看到的预览和下载的 Word 不一样，
  这是最坏的一类 bug）。这里直接读交付件本身，预览＝交付件，结构上不可能分叉。

python-docx 的段落/表格都在 body 里按顺序排列，按 body 的子元素顺序遍历即可。
"""
from __future__ import annotations

import html
import os

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

HEAD_CSS = """
<style>
 /* 预览页是独立文档，拿不到宿主的 CSS 变量，所以把站点那套值直接写死在这里，
    保证预览与站点其他页面的观感一致（主色 #0173C0、正文 #10131E、页底 #F3F5FB）。 */
 body{background:#F3F5FB;margin:0;padding:18px;color:#10131E;
      font:14px/1.65 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
 .pp-page{background:#FFF;max-width:820px;margin:0 auto;padding:46px 52px;
          border:1px solid #D9E1E7;border-radius:10px;box-shadow:0 1px 3px rgba(16,19,30,.05)}
 .pp-page p{margin:6px 0;line-height:1.9;font-size:14px;text-align:justify}
 .pp-page h1{font-size:19px;text-align:center;margin:10px 0 18px;font-weight:700}
 .pp-page h2{font-size:15px;margin:20px 0 8px;padding-left:9px;border-left:3px solid #0173C0}
 .pp-page table{border-collapse:collapse;width:100%;margin:10px 0;font-size:12.8px}
 .pp-page td,.pp-page th{border:1px solid #D9E1E7;padding:6px 9px;vertical-align:top}
 .pp-page td.pp-h{background:#F3F5FB;font-weight:700;width:26%}
 .pp-bar{max-width:820px;margin:0 auto 12px;color:#8B8F9E;font-size:12.5px}
 .pp-bar b{color:#0173C0}
 .pp-empty{color:#8B8F9E}
</style>
"""


def _style_of(par: Paragraph) -> str:
    name = (par.style.name or "") if par.style is not None else ""
    return name


def _para_html(par: Paragraph) -> str:
    txt = par.text or ""
    name = _style_of(par)
    if not txt.strip():
        return "<p>&nbsp;</p>"
    body = html.escape(txt)
    if "Heading 1" in name or name in ("Title",):
        return "<h1>%s</h1>" % body
    if "Heading" in name:
        return "<h2>%s</h2>" % body
    # 生成器用的是加粗段落当小标题（不是 Word 的 Heading 样式），
    # 预览里按"整段加粗且不长"识别成小标题，只为好读，不改动交付件本身。
    runs = [r for r in par.runs if (r.text or "").strip()]
    if runs and len(txt.strip()) <= 40 and all(r.bold for r in runs):
        return "<h2>%s</h2>" % body
    return "<p>%s</p>" % body


def _table_html(tb: Table) -> str:
    rows = []
    for r in tb.rows:
        cells = []
        for c in r.cells:
            t = " ".join((p.text or "").strip() for p in c.paragraphs).strip()
            cells.append("<td>%s</td>" % (html.escape(t) or "&nbsp;"))
        rows.append("<tr>%s</tr>" % "".join(cells))
    return "<table>%s</table>" % "".join(rows)


def docx_to_html(path: str, title: str = "") -> str:
    """读 docx → HTML 片段（不含 <html> 外壳，便于嵌 iframe）。"""
    doc = Document(path)
    out = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            out.append(_para_html(Paragraph(child, doc)))
        elif tag == "tbl":
            out.append(_table_html(Table(child, doc)))
    head = ('<div class="pp-bar">预览的是**交付件本身**（%s，%d 字节）—— '
            "看到的排版与下载的 Word 同源。</div>"
            % (html.escape(os.path.basename(path)), os.path.getsize(path)))
    head = head.replace("**", "")
    body = "".join(out) or '<p class="pp-empty">（这份文件里没有内容）</p>'
    return "%s%s<div class=\"pp-page\"><h1>%s</h1>%s</div>" % (
        HEAD_CSS, head, html.escape(title or "报告表（草稿）"), body)


def docx_to_blocks(path: str) -> list:
    """把 docx 拆成块（供接口返回结构化预览，如目录/字数统计）。"""
    doc = Document(path)
    blocks = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(child, doc)
            if (p.text or "").strip():
                blocks.append({"类型": "段落", "样式": _style_of(p), "文本": p.text})
        elif tag == "tbl":
            tb = Table(child, doc)
            blocks.append({"类型": "表格", "行数": len(tb.rows),
                           "首行": [c.text.strip() for c in tb.rows[0].cells] if tb.rows else []})
    return blocks