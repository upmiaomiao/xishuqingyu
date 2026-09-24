#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""① 解析层：环评报告 PDF → 页级结构化包（章节树 + 页级原文 + 表格 + 锚点索引 + 页号映射）。

设计要点（对应方案第 ① 层）：
  - **页级原文**：逐页存文本，页码 = 物理页号；另建「物理页 ↔ 印刷页号」映射，
    因为审核意见里的 "-P19" 用的是印刷页号（封面/目录会造成偏移）。
  - **章节树**：优先用 PDF 内置目录（get_toc），缺失时用编号/标题正则重建。
  - **表格**：find_tables + span 级单元格重建（见 pdfutil），输出 markdown 与二维表。
  - **锚点索引**：按审核项预置锚点词，给出命中页与上下文片段 —— 抽取层据此定位。
  - **页眉页脚清理**：跨页高频行（运行页眉/页脚）与纯页码行会被剔除，避免污染事实抽取。

产出可缓存为 JSON（默认 /data/eia_audit/parsed/<sha1>.json），解析一次可复现复用。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict

import fitz

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pdfutil import rows_of, to_markdown  # noqa: E402

# 审核项关心的锚点（与截图里的审核项一一对应）
DEFAULT_ANCHORS = {
    "编制依据": r"编制依据|评价依据",
    "分类管理名录": r"分类管理名录",
    "专项评价设置": r"专项评价",
    "评价等级": r"评价等级|评价工作等级",
    "环境敏感目标": r"环境保护目标|环境敏感目标|敏感目标",
    "原辅材料": r"原辅材料|主要原辅料|原辅料及",
    "产品方案": r"产品方案|生产规模|建设规模",
    "工艺流程": r"工艺流程|生产工艺",
    "产污环节": r"产污环节|污染源强|污染物产生",
    "水平衡": r"水平衡|用水平衡",
    "大气污染物": r"大气污染物|有组织排放|无组织排放",
    "二噁英": r"二噁英",
    "地表水": r"地表水",
    "地下水": r"地下水",
    "声环境": r"声环境|噪声",
    "土壤": r"土壤环境",
    "生态": r"生态环境|生态影响",
    "环境风险": r"环境风险|风险评价",
    "固体废物": r"固体废物|固废|炉渣|飞灰",
    "危废": r"危险废物|危废",
    "排污许可": r"排污许可",
    "总量控制": r"总量控制|总量指标",
    "环境监测": r"环境监测计划|监测计划",
    "公众参与": r"公众参与|公众意见",
    "结论": r"评价结论|结论与建议",
}

PAGENO_RE = re.compile(r"^[\s—–\-－_]*(\d{1,4})[\s—–\-－_]*$")
PAGENO_CN_RE = re.compile(r"^第\s*(\d{1,4})\s*页$")
# 报告自述页码标签：'1-2'（章-页）、'3.2-1'（章.节-页）等
PAGEMARK_RE = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)-(\d{1,3})$")
SEG_SPLIT_RE = re.compile(r"\s{3,}")
CHAPTER_RES = [
    re.compile(r"^第\s*([一二三四五六七八九十百]+)\s*章\s*(\S.{0,40})$"),
    re.compile(r"^(\d{1,2})\.\d?\s*(\S.{0,40})$"),
    re.compile(r"^(附件\s*\d+)\s*(\S.{0,40})?$"),
]
TOP_BAND, BOT_BAND = 0.07, 0.90          # 页眉/页脚带（占页高比例）
# 实测依据：临沂报告页眉 y1≈0.064h、页脚 y0≈0.926h；报告表页码 y0≈0.90~0.92h，
# 而正文行最低到 y0≈0.88h、页内小标题最高到 y1≈0.10h —— 故取 0.07/0.90 分界。


def _page_lines(page) -> list[str]:
    return [ln.strip() for ln in page.get_text("text", sort=True).splitlines() if ln.strip()]


def _band_lines(page) -> list:
    """页眉/页脚带内的文本行（含 bbox）。用位置而非内容判定，比按内容更稳。"""
    h = page.rect.height
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            txt = "".join(s["text"] for s in l["spans"]).strip()
            if not txt:
                continue
            y0, y1 = l["bbox"][1], l["bbox"][3]
            if y1 < h * TOP_BAND or y0 > h * BOT_BAND:
                out.append(txt)
    return out


def _norm(s: str) -> str:
    return re.sub(r"\d+", "#", s).strip()


def detect_running_lines(pages_lines, bands=None, min_ratio: float = 0.3) -> set:
    """跨页高频的页眉/页脚**片段**。

    页眉常是「项目名        01 概述」——整行按章变化，但项目名片段每页都在。
    因此先按 3 个以上空格切成片段，再按片段频次判定。
    """
    n = len(pages_lines)
    if n < 8:
        return set()
    cnt = {}
    for i, lines in enumerate(pages_lines):
        cand = bands[i] if bands else (lines[:3] + lines[-3:])
        segs = set()
        for ln in cand:
            for seg in SEG_SPLIT_RE.split(ln):
                seg = seg.strip()
                if 2 <= len(seg) <= 60:
                    segs.add(_norm(seg))
        for seg in segs:
            cnt[seg] = cnt.get(seg, 0) + 1
    return {k for k, v in cnt.items() if v / n >= min_ratio}


def strip_headers(pages_lines, bands, running: set) -> list:
    """剔除运行页眉/页脚片段与纯页码行；保留页眉里仍有信息的部分（如章号标记）。"""
    out = []
    for lines, cand in zip(pages_lines, bands):
        cand_set = set(cand)
        keep = []
        for ln in lines:
            if ln in cand_set:
                if PAGENO_RE.match(ln) or PAGENO_CN_RE.match(ln) or PAGEMARK_RE.match(ln):
                    continue
                parts = [p for p in SEG_SPLIT_RE.split(ln)
                         if p.strip() and _norm(p.strip()) not in running
                         and not PAGENO_RE.match(p.strip())
                         and not PAGENO_CN_RE.match(p.strip())
                         and not PAGEMARK_RE.match(p.strip())]
                rest = " ".join(p.strip() for p in parts).strip()
                # 片段被剔到只剩标点/极短 → 整行丢弃
                if len(re.sub(r"[\s\W_]", "", rest)) < 2:
                    continue
                keep.append(rest)
            else:
                if PAGENO_RE.match(ln) or PAGENO_CN_RE.match(ln):
                    continue
                keep.append(ln)
        out.append(keep)
    return out


def build_page_labels(pages_lines, bands) -> tuple:
    """返回（物理页→印刷页号, 物理页→报告自述页标签文本）。

    印刷页号要求整体单调递增；页标签（如 '3-8' 章-页）原样保留，用于消除歧义。
    """
    labels, marks = {}, {}
    for i, cand in enumerate(bands):
        for ln in (cand[::-1] + cand):
            m = PAGENO_RE.match(ln) or PAGENO_CN_RE.match(ln)
            if m:
                labels[i + 1] = int(m.group(1))
                break
        for ln in (cand[::-1] + cand):
            m = PAGEMARK_RE.match(ln)
            if m:
                marks[i + 1] = ln
                break
    good, last = {}, None
    for phys in sorted(labels):
        v = labels[phys]
        if last is None or v > last:
            good[phys] = v
            last = v
    return (good if len(good) >= max(3, len(labels) // 2) else {}), marks


def sha1_of(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_chapters(doc, pages_lines: list[list[str]]) -> list:
    toc = doc.get_toc(simple=True) or []
    if len(toc) >= 5:
        return [{"level": lvl, "title": title.strip(), "page": pg, "from_toc": True}
                for lvl, title, pg in toc]
    out = []
    for i, lines in enumerate(pages_lines, start=1):
        for ln in lines[:6]:
            for rx in CHAPTER_RES:
                m = rx.match(ln)
                if m:
                    out.append({"level": 1, "title": ln, "page": i, "from_toc": False})
                    break
            else:
                continue
            break
    return out


@dataclass
class ParsedReport:
    pdf: str
    sha1: str
    pages: int
    page_text: list = field(default_factory=list)
    toc: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    anchors: dict = field(default_factory=dict)
    page_labels: dict = field(default_factory=dict)
    page_marks: dict = field(default_factory=dict)
    running_lines: list = field(default_factory=list)
    empty_pages: list = field(default_factory=list)
    page_offset: int = None          # 物理页 - 印刷页；报告无绝对页码时为 None
    meta: dict = field(default_factory=dict)

    # ---- 便利检索 ----
    def search(self, pattern: str, max_hits: int = 50, ctx: int = 60) -> list:
        rx = re.compile(pattern)
        hits = []
        for i, t in enumerate(self.page_text, start=1):
            for m in rx.finditer(t):
                hits.append({"page": i,
                             "printed_page": self.page_labels.get(str(i)),
                             "mark": self.page_marks.get(str(i)),
                             "match": m.group(0),
                             "snippet": re.sub(r"\s+", " ", t[max(0, m.start() - ctx): m.end() + ctx]).strip()})
                if len(hits) >= max_hits:
                    return hits
        return hits

    def text_range(self, a: int, b: int) -> str:
        return "\n".join(self.page_text[a - 1: b])

    def printed_page(self, phys: int):
        """物理页 → 印刷页号（审核意见里 -P19 用的是印刷页号；无标注返回 None）。"""
        return self.page_labels.get(str(phys))

    def phys_page(self, printed: int):
        """印刷页号 → 物理页（供抽取层把报告自述页码换算成可核验的物理页）。"""
        for k, v in self.page_labels.items():
            if v == printed:
                return int(k)
        return None

    def to_json(self) -> dict:
        return asdict(self)


def parse_pdf(path: str, with_tables: bool = True, table_pages=None,
              anchors: dict = None, verbose: bool = False) -> ParsedReport:
    doc = fitz.open(path)
    n = doc.page_count
    pages_lines = [_page_lines(doc[i]) for i in range(n)]
    bands = [_band_lines(doc[i]) for i in range(n)]
    running = detect_running_lines(pages_lines, bands)
    stripped = strip_headers(pages_lines, bands, running)
    page_text = ["\n".join(lines) for lines in stripped]
    labels, marks = build_page_labels(pages_lines, bands)
    chapters = build_chapters(doc, stripped)

    tables = []
    if with_tables:
        span = range(n) if table_pages is None else table_pages
        for i in span:
            for pno, rows in rows_of(doc[i]):
                md = to_markdown(rows)
                if not md:
                    continue
                flat = "".join("".join(r) for r in rows)
                if len(flat) < 8:
                    continue
                tables.append({"page": pno + 1, "printed_page": labels.get(pno + 1),
                               "mark": marks.get(pno + 1),
                               "rows": rows, "markdown": md})
            if verbose and (i + 1) % 50 == 0:
                print(f"    …已解析 {i + 1}/{n} 页，表格 {len(tables)} 张", flush=True)

    anchor_index = {}
    for name, rx in (anchors or DEFAULT_ANCHORS).items():
        found = []
        rxc = re.compile(rx)
        for i, t in enumerate(page_text, start=1):
            m = rxc.search(t)
            if m:
                found.append({"page": i, "printed_page": labels.get(i),
                              "mark": marks.get(i),
                              "match": m.group(0),
                              "snippet": re.sub(r"\s+", " ", t[max(0, m.start() - 50): m.end() + 50]).strip()})
        anchor_index[name] = found[:20]

    meta = dict(doc.metadata or {})
    # 无文本层页（纯图/扫描页）：抽取层不得引用这些页作为事实来源
    empty = [i + 1 for i, t in enumerate(page_text) if len(t.strip()) < 20]
    # 印刷页号偏移：取众数（物理页 - 印刷页）
    offs = [k - v for k, v in labels.items()]
    offset = max(set(offs), key=offs.count) if offs else None
    rep = ParsedReport(pdf=os.path.abspath(path), sha1=sha1_of(path), pages=n,
                       page_text=page_text,
                       toc=chapters,
                       tables=tables,
                       anchors=anchor_index,
                       page_labels={str(k): v for k, v in labels.items()},
                       page_marks={str(k): v for k, v in marks.items()},
                       running_lines=sorted(running),
                       empty_pages=empty,
                       page_offset=offset,
                       meta={"title": (meta.get("title") or "").strip(),
                             "chars": sum(len(t) for t in page_text)})
    doc.close()
    return rep


def load_or_parse(path: str, cache_dir: str = None, **kw) -> ParsedReport:
    cache_dir = cache_dir or os.environ.get("EIA_PARSE_CACHE", "")
    if cache_dir:
        os.makedirs(cache_dir, exist_ok=True)
        cp = os.path.join(cache_dir, sha1_of(path) + ".json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                return ParsedReport(**json.load(f))
    rep = parse_pdf(path, **kw)
    if cache_dir:
        with open(cp, "w", encoding="utf-8") as f:
            json.dump(rep.to_json(), f, ensure_ascii=False)
    return rep