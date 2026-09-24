# -*- coding: utf-8 -*-
"""批注版 PDF 导出：把审核意见作为**真实 PDF 批注**写进报告副本。

用户 2026-09-22 拍板的形态与约束：
  · 交付件 = **原件 + 批注**，原文件一个字节都不改，另存 `<stem>.批注版.pdf`；
  · 三档定位（精确 / 近似 / 仅页码）**必须写明档位**；
  · 版面里框不出来就**不画高亮**（宁可只挂页码批注）—— 假高亮比没有高亮更糟：
    用户会以为高亮处就是报告原话；
  · 末尾追加「审核意见汇总」页 + 落款栏（审核单位/审核人/审核日期/报告名称）。

为什么不用 `page.search_for(摘录)`（实测数据，别再走回头路）：
  · 整条摘录命中率只有 34%；
  · 退化成"片段搜索"后会返回 6pt 宽的竖排窄条 —— 高亮落在半个字上。
改用**字符级 bbox**：把整页拆成「非空白字符 + bbox」序列（下标天然对齐，
不存在文本与坐标错位的问题），匹配时把摘录也去掉空白再比。空白、换行、分栏、
表格单元格之间的间隔全都不用管。
"""
from __future__ import annotations

import os
import re
from typing import Iterable

import pymupdf

from .audit_anchor import LEVEL_EXACT, LEVEL_NEAR, LEVEL_NONE, LEVEL_PAGE

# 批注配色：精确=黄底高亮，近似=蓝色下划线，表格=蓝色方框，仅页码=页边批注图标
C_EXACT = (1, 0.92, 0.35)
C_NEAR = (0.16, 0.55, 0.90)
C_TABLE = (0.16, 0.55, 0.90)
C_PAGE = (0.55, 0.58, 0.62)

A4 = (595.0, 842.0)
FONT = "china-s"                      # pymupdf 内置中文字体（Droid Sans Fallback）
FONT_B = "china-s"
# 西文/数字用内置 Helvetica：china-s 把 ASCII 也按全角推进（"P 1 7 7"很松散），
# 而且它的 text_length 与"1 em/字"的实际渲染对不上。Base-14 不需要嵌入字体文件。
LAT_FONT = "helv"

_SEV_ORDER = ["存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用"]


# ================================================================ 版面定位

def page_chars(page) -> tuple:
    """整页「非空白字符 + bbox」序列（按 sort=True 的阅读顺序）。

    刻意**不收空白字符**：匹配时两边都去掉空白再比，于是换行、分栏、
    表格单元格之间的间隔都不影响定位，也不会出现"文本下标与 bbox 下标错位"
    —— 错位就会把高亮画在别的字上，而且看不出来。
    """
    text, boxes = [], []
    for b in page.get_text("rawdict", sort=True).get("blocks", []):
        for ln in b.get("lines", []):
            for sp in ln.get("spans", []):
                for ch in sp.get("chars", []):
                    c = ch.get("c") or ""
                    if c and not c.isspace() and c != "\u3000":
                        text.append(c)
                        boxes.append(ch.get("bbox"))
    return "".join(text), boxes


def _squeeze(s: str) -> str:
    return re.sub(r"[\s\u3000]+", "", s or "")


def rects_of(boxes: list, start: int, end: int, tol: float = 6.0) -> list:
    """字符区间 → 按行分组的矩形（行内取并集，跨行给多个矩形）。"""
    picked = [b for b in boxes[start:end] if b]
    if not picked:
        return []
    picked.sort(key=lambda r: (round(r[1], 1), r[0]))
    rows, cur = [], [picked[0]]
    for r in picked[1:]:
        if abs((r[1] + r[3]) / 2 - (cur[-1][1] + cur[-1][3]) / 2) <= tol:
            cur.append(r)
        else:
            rows.append(cur)
            cur = [r]
    rows.append(cur)
    out = []
    for row in rows:
        out.append(pymupdf.Rect(min(r[0] for r in row), min(r[1] for r in row),
                                max(r[2] for r in row), max(r[3] for r in row)))
    return out


def find_rects(text: str, boxes: list, needle: str) -> list:
    """在页面字符序列里找 needle（去空白比对），返回矩形列表。"""
    q = _squeeze(needle)
    if len(q) < 3:
        return []
    i = text.find(q)
    if i < 0:
        return []
    return rects_of(boxes, i, i + len(q))


def _runs(needle: str, min_len: int = 6) -> list:
    """摘录里较长的连续片段（整条找不到时退一步用，长的优先）。"""
    segs = [s for s in re.split(r"[\s\u3000]+", needle or "") if len(_squeeze(s)) >= min_len]
    segs.sort(key=len, reverse=True)
    return segs


# ================================================================ 批注计划

def plan_marks(anchors: Iterable[dict], doc) -> tuple:
    """算出"每一页要画什么"，只读 PDF，不写任何东西。

    返回 (plan, stat)：plan[物理页] = [mark,...]；
    stat 记录每个档位"框出来多少 / 只能挂页边多少"，用于导出后自检与汇报。
    """
    plan: dict = {}
    stat = {"精确": [0, 0], "近似": [0, 0], "仅页码": [0, 0], "无证据": [0, 0]}   # [可框, 只能挂页边]
    cache: dict = {}

    for a in anchors:
        pg = a.get("page")
        lv = a.get("level") or LEVEL_PAGE
        if not pg or not (1 <= pg <= doc.page_count):
            # 「无证据」条目本来就没有页码，不进统计（它不产生批注，也不是定位失败）；
            # 真有页码却越界的才算异常，单独记一笔。
            if lv != LEVEL_NONE:
                stat.setdefault(lv, [0, 0])[1] += 1
            continue
        if pg not in cache:
            text, boxes = page_chars(doc[pg - 1])
            cache[pg] = (text, boxes)
        text, boxes = cache[pg]
        mark = {
            "level": lv, "item": a.get("item"), "审核项": a.get("审核项") or "",
            "结论": a.get("结论") or "", "类别": a.get("类别") or "",
            "参考依据": a.get("参考依据") or "", "理由": a.get("理由") or "",
            "quote": a.get("quote") or "", "hit": a.get("hit") or "",
            "printed": a.get("printed"), "置信度": a.get("置信度") or "",
            "需人工确认": a.get("需人工确认") or [],
        }
        done = False
        if lv == LEVEL_EXACT:
            rects = find_rects(text, boxes, a.get("hit") or a.get("quote"))
            if not rects:
                for seg in _runs(a.get("hit") or a.get("quote"), 6):
                    rects = find_rects(text, boxes, seg)
                    if rects:
                        mark["hit"] = seg
                        mark["why"] = "整条未能在版面框出，按片段「%s」框出" % seg[:18]
                        break
            if rects:
                mark["kind"] = "highlight"
                mark["rects"] = rects
                mark.setdefault("why", "与原文逐字一致")
                done = True
        elif lv == LEVEL_NEAR:
            if a.get("table") is not None:
                try:
                    tbs = doc[pg - 1].find_tables().tables
                    ti = int(a["table"])
                    if ti < len(tbs) and tbs[ti].bbox:
                        mark["kind"] = "rect"
                        mark["rects"] = [pymupdf.Rect(tbs[ti].bbox)]
                        mark["why"] = "按表格内容定位到本页第 %d 张表" % (ti + 1)
                        done = True
                except Exception:
                    pass
            if not done:
                rects = find_rects(text, boxes, a.get("hit"))
                if not rects:
                    for seg in _runs(a.get("hit"), 4):
                        rects = find_rects(text, boxes, seg)
                        if rects:
                            mark["hit"] = seg
                            break
                if rects:
                    mark["kind"] = "underline"
                    mark["rects"] = rects
                    mark.setdefault("why", "按关键词定位，可能有偏移")
                    done = True
        if not done:
            mark["kind"] = "note"                     # 页边批注：只标页码，不画高亮
            mark["why"] = a.get("why") or ""
            if lv == LEVEL_EXACT:
                mark["why"] = "（精确档）" + mark["why"] + "；本页版面里未能框出原文，仅按页码定位"
            stat.setdefault(lv, [0, 0])[1] += 1
        else:
            stat.setdefault(lv, [0, 0])[0] += 1
        plan.setdefault(pg, []).append(mark)
    return plan, stat


def _annot_text(m: dict) -> tuple:
    """批注的标题与内容。内容要**自解释**：只看到气泡的人也得知道这是哪个档位。"""
    title = "AI审核·%s·第%s条" % (m["level"], m.get("item") or "?")
    lines = [
        "【%s】%s" % (m["结论"] or "（无结论）", m["审核项"]),
        "类别：%s" % m["类别"],
        "定位：%s（%s）" % (m["level"], m.get("why") or ""),
    ]
    if m.get("hit") and m["hit"] != m.get("quote"):
        lines.append("命中原文：%s" % m["hit"][:120])
    if m.get("quote"):
        lines.append("证据摘录：%s" % m["quote"][:300])
    if m.get("参考依据"):
        lines.append("参考依据：%s" % m["参考依据"][:300])
    if m.get("理由"):
        lines.append("理由：%s" % m["理由"][:400])
    if m.get("置信度"):
        lines.append("置信度：%s" % m["置信度"])
    for c in m.get("需人工确认") or []:
        lines.append("需人工确认：%s" % c)
    lines.append("※ 定位档位：精确=与原文逐字一致；近似=按关键词/表格定位，可能有偏移；"
                 "仅页码=只能按页码核对。人工复核结论以审核意见书为准。")
    return title, "\n".join(lines)


def annotate(doc, plan: dict) -> dict:
    """按计划把批注写进 doc（内存中的副本），返回写入计数。"""
    n = {"highlight": 0, "underline": 0, "rect": 0, "note": 0}
    for pg, marks in plan.items():
        page = doc[pg - 1]
        for m in marks:
            title, content = _annot_text(m)
            try:
                if m["kind"] == "highlight":
                    an = page.add_highlight_annot(m["rects"])
                    an.set_colors(stroke=C_EXACT)
                elif m["kind"] == "underline":
                    an = page.add_underline_annot(m["rects"])
                    an.set_colors(stroke=C_NEAR)
                elif m["kind"] == "rect":
                    an = page.add_rect_annot(m["rects"][0])
                    an.set_colors(stroke=C_TABLE)
                else:
                    # 页边批注：贴右上角，避开正文；图标在阅读器里可点开
                    pt = pymupdf.Point(page.rect.width - 26, 26)
                    an = page.add_text_annot(pt, content)
                    an.set_colors(stroke=C_PAGE)
                an.set_info(title=title[:120], content=content[:2000])
                an.update()
                n[m["kind"]] += 1
            except Exception:
                # 单条批注失败不能连累整份导出：退化成页边批注
                try:
                    an = page.add_text_annot(pymupdf.Point(page.rect.width - 26, 26),
                                             content + "\n※ 本条版面批注写入失败，仅保留文字说明")
                    an.set_info(title=title[:120])
                    an.update()
                    n["note"] += 1
                except Exception:
                    pass
    return n


# ================================================================ 汇总页

def _is_lat(ch: str) -> bool:
    """可打印 ASCII 才交给西文字体。

    门槛**不能按"是不是 CJK 区"来划**：`…`（U+2026）、`—`、`□`（U+25A1）都落在 ASCII 以外
    却在中文字体里，交给 helv 会画成空白方框。所以只放 ASCII 过去，其余一律中文字体。
    """
    return 0x20 <= ord(ch) <= 0x7E


def _font_runs(s: str):
    """把字符串切成 (是否西文, 片段) 运行块，供混排绘制。"""
    out, cur, lat = [], "", None
    for ch in s:
        now = _is_lat(ch)
        if lat is None or now == lat:
            cur += ch
        else:
            out.append((lat, cur))
            cur = ch
        lat = now
    if cur:
        out.append((lat, cur))
    return out


class _Writer:
    """极简排版器：按 pt 逐行写，量准了再换行。

    **中西混排**：ASCII 用内置 Helvetica（比例字体，`text_length` 准），中文用 `china-s`。
    服务器上没有中文字体文件（只有 DejaVu），Helvetica 是 PDF 内置 Base-14，不需要额外依赖。
    """

    def __init__(self, page, x0=48.0, y0=56.0, x1=None):
        self.page = page
        self.x0 = x0
        self.x1 = (x1 if x1 is not None else page.rect.width - 48.0)
        self.y = y0
        self.font = pymupdf.Font(FONT)
        self.fontL = pymupdf.Font(LAT_FONT)
        self.bottom = page.rect.height - 56.0

    def runw(self, seg, lat, size):
        """单个运行块的宽度。"""
        if lat:
            return self.fontL.text_length(seg, fontsize=size)
        # 中文字体里**每个字符都按 1 em 推进**（含全角标点，实测 len×size 分毫不差）。
        # 不要改成 Font("china-s").text_length()：它对中文准，对数字/英文/空格低估 1.7~2.4 倍
        # （「HJ/T169-2018」量出 57.4pt、实际渲出 114.0pt），按它折行会把字顶出页面
        # （表头第三行压到第一行数据上、最后一列被页边裁掉）。实测表见 量字体宽度.py。
        return len(seg) * size

    def width(self, s, size):
        return sum(self.runw(seg, lat, size) for lat, seg in _font_runs(s))

    def text(self, x, y, s, size):
        """在 (x,y) 画一段混排文字，返回结束时的 x。"""
        for lat, seg in _font_runs(s):
            self.page.insert_text((x, y), seg,
                                  fontname=(LAT_FONT if lat else FONT), fontsize=size)
            x += self.runw(seg, lat, size)
        return x

    def wrap(self, s, size, indent=0.0):
        """按可用宽度贪心折行（中文没有词边界，按字符折即可）。"""
        return self.wrapw(s, size, self.x1 - self.x0 - indent)

    def wrapw(self, s, size, avail):
        """按指定宽度折行。

        单元格必须用这个：`wrap()` 用的是**整页**可用宽度，写进窄列时文字会
        直接顶穿单元格、跑出页面右边界（实测渲图看到最后一列被页边裁掉）。
        """
        out, cur = [], ""
        for ch in s:
            if self.width(cur + ch, size) > avail:
                out.append(cur)
                cur = ch
            else:
                cur += ch
        if cur:
            out.append(cur)
        return out or [""]

    def line(self, s, size=9.5, indent=0.0, gap=None, bold=False):
        for seg in self.wrap(s, size, indent):
            if self.y > self.bottom:
                return False
            self.text(self.x0 + indent, self.y, seg, size)
            self.y += gap if gap is not None else size * 1.62
        return True

    def rule(self, gap_before=4.0, gap_after=6.0, width=0.7):
        self.y += gap_before
        self.page.draw_line((self.x0, self.y), (self.x1, self.y), width=width)
        self.y += gap_after

    def space(self, h=6.0):
        self.y += h


def _cell(w: "_Writer", x, y, wpt, s, size=9.0, pad=3.0, max_lines=3):
    """在 (x,y,wpt) 单元格里写字，返回实际行数。折行宽度 = 单元格宽 − 左右内边距。"""
    avail = max(12.0, wpt - 2 * pad)
    lines = w.wrapw(s, size, avail)
    if len(lines) > max_lines:
        # 截断要看得出来：末行补省略号，否则读的人会以为理由本来就这么短
        lines = lines[:max_lines]
        last = lines[-1]
        while last and w.width(last + "…", size) > avail:
            last = last[:-1]
        lines[-1] = last + "…"
    for i, seg in enumerate(lines):
        w.text(x + pad, y + size * 1.25 + i * size * 1.42, seg, size)
    return max(1, len(lines))


def _fill(w: "_Writer", label, spec, size=10.5, gap=26.0):
    """签字栏的一行：标签 + 留白横线（+ 若干文字）。

    **横线是画出来的，不是打一串下划线字符**：ASCII `_` 在 china-s 里的实际推进宽度
    与 `text_length` 量出来的不一致，56 个下划线会把"报告名称"这一行直接顶出页面右边界
    （渲染成图片才看出来 —— 文本层面一切"正常"）。
    spec 里 ("blank", None) 表示吃掉剩下的宽度，("blank", 60) 表示固定 60pt。
    """
    x = w.x0
    w.text(x, w.y, label, size)
    x += w.width(label, size) + 4
    gapx = 6.0
    fixed = sum(v for kind, v in spec if kind == "blank" and v)
    texts = sum(w.width(v, size) for kind, v in spec if kind == "text")
    nflex = sum(1 for kind, v in spec if kind == "blank" and not v)
    rest = w.x1 - x - fixed - texts - gapx * max(0, len(spec) - 1)
    flexw = max(40.0, rest / nflex) if nflex else 0.0
    for kind, v in spec:
        if kind == "text":
            w.text(x, w.y, v, size)
            x += w.width(v, size) + gapx
        else:
            bw = v or flexw
            w.page.draw_line((x, w.y + 2.5), (x + bw, w.y + 2.5), width=0.6)
            x += bw + gapx
    w.y += gap
    return x


def draw_summary(doc, result: dict, anchors: list, review: dict, stat: dict) -> int:
    """在文档末尾追加「审核意见汇总」页（可能多页）。返回追加的页数。"""
    f = result.get("file") or {}
    st = result.get("统计") or {}
    items = result.get("items") or []
    added = 0
    page = doc.new_page(width=A4[0], height=A4[1])
    added += 1
    w = _Writer(page)

    w.line("审核意见汇总", 16, gap=22)
    w.line("项目名称：%s" % (f.get("项目名称") or "（未识别）"), 10)
    w.line("报告文件：%s" % (f.get("name") or ""), 9.5)
    w.line("文件类型：%s　　报告页数：%s 页　　审核项：%s 项"
           % (f.get("环评文件类型") or "—", f.get("pages") or "—", len(items)), 9.5)
    w.line("AI 审核统计：" + "　".join("%s %d" % (k, st.get(k, 0)) for k in _SEV_ORDER), 9.5)
    w.line("批注定位统计：" + "　".join(
        "%s %d 条（版面框出 %d）" % (k, sum(stat.get(k, [0, 0])), stat.get(k, [0, 0])[0])
        for k in ("精确", "近似", "仅页码", "无证据")), 9.5)
    w.space(2)
    w.line("说明：本页为审核意见汇总，正文中的批注按定位档位分色 —— "
           "精确＝黄底高亮（与原文逐字一致）；近似＝蓝色下划线或蓝框（按关键词/表格定位，可能有偏移）；"
           "仅页码＝页边批注（只在页边标注，正文里不作高亮）。三档都可点击批注查看依据与理由。", 9)
    w.line("「证据页」列：数字为 PDF 物理页，括号内为报告印刷页（若有）；"
           "摘要列过长时以「…」截断，完整理由见批注或审核意见书。", 9)
    w.space(4)

    # ---- 明细表
    # 列宽是一处定义、两处使用（表头/表体），别再各写一份数字 —— 上一版就是那样，
    # 改列宽时漏改一处就会错列。
    cols = [("序号", 28), ("审核项", 88), ("结论", 58), ("人工复核", 58),
            ("证据页", 46), ("依据与理由摘要", 0)]
    widths = [wd for _, wd in cols]
    widths[-1] = w.x1 - w.x0 - sum(widths[:-1])
    head_y = w.y
    w.page.draw_rect(pymupdf.Rect(w.x0, head_y, w.x1, head_y + 16), width=0.6)
    cx = w.x0
    for (name, _), wd in zip(cols, widths):
        _cell(w, cx, head_y, wd, name, 8.6)
        cx += wd
    w.y = head_y + 17
    for i, it in enumerate(items, 1):
        k = it.get("审核项") or ""
        rv = (review or {}).get(k) or {}
        ev = it.get("证据") or []
        pgs = "、".join(
            "P%s%s" % (e.get("page"), ("(印刷%s)" % e["mark"]) if e.get("mark") else "")
            for e in ev[:3] if e.get("page")) or "—"
        brief = (it.get("理由") or "")[:200]
        cells = [str(i), k, it.get("AI审核") or "", rv.get("人工修改") or "", pgs, brief]
        nlines = 1
        cx = w.x0
        for j, val in enumerate(cells):
            nl = _cell(w, cx, w.y, widths[j], val, 8.4,
                       max_lines=4 if j == len(cells) - 1 else 3)
            nlines = max(nlines, nl)
            cx += widths[j]
        h = max(16.0, 8.4 * 1.42 * nlines + 6)
        # 表格线
        w.page.draw_rect(pymupdf.Rect(w.x0, w.y, w.x1, w.y + h), width=0.4)
        cx = w.x0
        for wd in widths[:-1]:
            cx += wd
            w.page.draw_line((cx, w.y), (cx, w.y + h), width=0.4)
        w.y += h + 2
        if w.y > w.bottom - 60:
            page = doc.new_page(width=A4[0], height=A4[1])
            added += 1
            w = _Writer(page)
            w.line("审核意见汇总（续）", 13, gap=20)

    # ---- 落款栏（用户 2026-09-22 明确要保留）
    if w.y > w.bottom - 130:                 # 落款不能被挤到页外：宁可另起一页
        page = doc.new_page(width=A4[0], height=A4[1])
        added += 1
        w = _Writer(page)
        w.line("审核意见汇总（落款）", 13, gap=22)
    w.space(10)
    w.rule(gap_before=2, gap_after=12)
    w.line("审核结论（人工）：□ 同意出具　□ 修改后出具　□ 需重新审核", 10, gap=22)
    w.space(4)
    _fill(w, "审核单位（盖章）：", [("blank", None)])
    _fill(w, "审　核　人：", [("blank", None), ("text", "（签字）")])
    _fill(w, "审核日期：", [("blank", None), ("text", "年"), ("blank", 60.0),
                            ("text", "月"), ("blank", 60.0), ("text", "日")])
    _fill(w, "报告名称：", [("blank", None)], gap=20)
    w.space(6)
    w.line("本汇总由审核系统自动生成，审核意见需经审核人复核签字后生效。", 8.5)
    return added


# ================================================================ 对外入口

def export_pdf(name: str, pdf_path: str, result: dict, parsed: dict, anchors: list,
               out_dir: str, review: dict = None, dry: bool = False) -> dict:
    """导出批注版 PDF。返回 {ok, file, path, marks, 定位, 页数, 说明}。"""
    doc = pymupdf.open(pdf_path)
    try:
        # 加密报告要显式认证：不然 annotate/save 会在写盘那一步才炸，
        # 用户看到的是"导出失败"，看不出是加密导致的。
        if doc.needs_pass and not doc.authenticate(""):
            return {"ok": False, "error": "该 PDF 已加密且空口令打不开，无法生成批注版"}
        plan, stat = plan_marks(anchors, doc)
        if dry:
            return {"ok": True, "dry": True, "定位": stat, "页数": len(plan),
                    "marks": sum(len(v) for v in plan.values())}
        os.makedirs(out_dir, exist_ok=True)
        stem = name.rsplit(".", 1)[0]
        out = os.path.join(out_dir, stem + ".批注版.pdf")
        before = doc.page_count
        n = annotate(doc, plan)
        added = draw_summary(doc, result, anchors, review or {}, stat)
        # garbage/deflate 只清理未引用对象并压缩流，不动原有页面的可见内容
        doc.save(out, garbage=3, deflate=True)
        total = doc.page_count
    finally:
        doc.close()
    return {"ok": True, "file": os.path.basename(out), "path": out,
            "marks": sum(len(v) for v in plan.values()), "批注": n,
            "定位": stat, "原页数": before, "汇总页": added, "总页数": total}


def main(argv=None):
    """命令行（服务器上排查用）：--dry 只报定位覆盖率，不写文件。"""
    import argparse
    import glob
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    audit_home = os.environ.get("AUDIT_HOME", "/data/eia_audit")
    if audit_home not in sys.path:            # 审核引擎（audit.*）在 AUDIT_HOME 下
        sys.path.insert(0, audit_home)
    from xishu_pipeline.audit_anchor import build_anchors, load_parsed, load_result

    ap = argparse.ArgumentParser()
    ap.add_argument("name", nargs="?", help="报告文件名；不给则跑全部有结果的报告")
    ap.add_argument("--reports", default="/data/eia_reports")
    ap.add_argument("--out", default="/data/eia_audit/_审核结果/导出")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args(argv)

    names = [a.name] if a.name else [j[:-5] + ".pdf"
                                     for j in sorted(os.listdir(os.path.join(audit_home, "_审核结果")))
                                     if j.endswith(".json")]
    for nm in names:
        try:
            res = load_result(nm)
        except FileNotFoundError:
            continue
        if not res.get("file"):          # _审核结果 下还放着别的 json，不是审核结果就跳过
            continue
        fname = res["file"]["name"]
        path = next((p for p in glob.glob(os.path.join(a.reports, "**", "*.pdf"), recursive=True)
                     if os.path.basename(p) == fname), None)
        if not path:
            print("找不到 PDF：", fname)
            continue
        parsed = load_parsed(fname, path, allow_parse=False)
        anchors = build_anchors(res, parsed)
        r = export_pdf(fname, path, res, parsed, anchors, a.out, dry=a.dry)
        print("%-46s 批注 %3d 条  定位 %s" % (fname[:46], r["marks"],
              {k: v for k, v in r["定位"].items()}))
        if not a.dry:
            print("    → %s（%d 页 + 汇总 %d 页 = %d 页）" % (r["file"], r["原页数"], r["汇总页"], r["总页数"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
