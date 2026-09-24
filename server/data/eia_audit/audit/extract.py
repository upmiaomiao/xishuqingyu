#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""② 抽取层：从报告结构化包里抽出审核需要的事实，**每项强制带页码与原文**。

原则（防编造的地基）：
  1. **抽不到就留空**，绝不填默认值。缺失的事实由判据层降级为「存在疑似问题」。
  2. 每项事实必须带 `page` + `quote`；`quote` 必须能在该页原文里机械检索到（验收三查之一）。
  3. 优先**表驱动**（报告的关键事实几乎都在表里），正则次之，模型只作兜底且同样要带页码原文。

抽取目标（对应方案 ② 层的 schema）：
  basic{项目名称, 环评文件类型, 行业类别, 建设单位, 建设地点}
  materials[{名称, 数量, 单位, 页码, 原文}]        ← 表驱动
  risk_materials[{名称, 最大贮存量t, 临界量t, 页码, 原文}]  ← 表驱动
  special_stated{element: 是否设置专项评价, 页码, 原文}     ← 报告自述
  sensitive_targets[{名称, 距离m, 方位, 页码, 原文}]        ← 表驱动
  special_inputs{element: 判据输入}                        ← 由上述事实机械推导
"""
from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field, asdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

# ---- 表头特征（用于表驱动识别） ----
NAME_COLS = ("名称", "货物名称", "物料名称", "原料名称", "材料名称", "物质名称", "污染物")
QTY_COLS = ("数量", "年用量", "用量", "年消耗", "消耗量", "最大贮存量", "最大存在量", "贮存量", "存在量")
UNIT_COLS = ("单位",)
DIST_COLS = ("距离", "距厂界", "最近距离", "方位及距离", "相对方位及距离")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _find_col(header: list, keys: tuple):
    for i, c in enumerate(header):
        if any(k in c for k in keys):
            return i
    return None


# 单位可能写在列名里（报告表常见：「改建完成后t/a」「年用量（t/a）」），
# 此时没有独立的"单位"列 —— 只认独立单位列会整张表漏掉（玻璃报告表 表2-8 就是这样漏的）。
UNIT_IN_HEADER = re.compile(r"(万\s*t/a|t/a|t·a|吨/年|吨/小时|t/h|万\s*m3/a|m3/a|Nm3/h|"
                            r"万\s*kWh/a|kWh/a|万\s*立方米/年|立方米/年|吨|万\s*吨|台|套|个|只|头|羽|亩|kW|MW)")


def unit_from_header(colname: str) -> str:
    m = UNIT_IN_HEADER.search(colname or "")
    return m.group(1).replace(" ", "") if m else ""


def _num(s: str):
    """从单元格里取数：'54.75 万' / '2.2' / '1500t/d' → (值, 单位提示)。"""
    if not s:
        return None, ""
    s = s.replace(",", "").replace("，", "")
    m = re.search(r"(\d+(?:\.\d+)?)", s)
    if not m:
        return None, ""
    v = float(m.group(1))
    tail = s[m.end():].strip()
    head = s[:m.start()].strip()
    unit = (head + " " + tail).strip() if head and not re.search(r"[\u4e00-\u9fffA-Za-z]$", head) else tail
    if "万" in s[:m.start()] or "万" in tail:
        v *= 1e4
        unit = unit.replace("万", "")
    return v, _norm(unit)


@dataclass
class Field:
    """一条事实。page/quote 为必填，缺失即视为未抽到。"""
    value: object = None
    page: int = None
    quote: str = ""
    method: str = ""            # table | regex | llm | derived
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.value is not None and self.page is not None and bool(self.quote.strip())


@dataclass
class Extraction:
    pdf: str
    basic: dict = field(default_factory=dict)
    materials: list = field(default_factory=list)
    risk_materials: list = field(default_factory=list)
    special_stated: dict = field(default_factory=dict)
    sensitive_targets: list = field(default_factory=list)
    special_inputs: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_json(self):
        return asdict(self)


# ---------------------------------------------------------------- 表驱动
def tables_with_header(rep, need_name=True, need_qty=False, need_unit=False,
                       need_dist=False, pages=None):
    """找表头符合列特征的表格。"""
    out = []
    for t in rep.tables:
        if pages and t["page"] not in pages:
            continue
        head = t["rows"][0] if t["rows"] else []
        # 表头可能跨两行（合并单元格），合并前两行一起看
        head2 = (t["rows"][0] + t["rows"][1]) if len(t["rows"]) > 1 else head
        if need_name and _find_col(head2, NAME_COLS) is None:
            continue
        if need_qty and _find_col(head2, QTY_COLS) is None:
            continue
        if need_unit and _find_col(head2, UNIT_COLS) is None:
            continue
        if need_dist and _find_col(head2, DIST_COLS) is None:
            continue
        out.append(t)
    return out


def near_pages(rep, anchor: str, radius: int = 2) -> set:
    hs = rep.anchors.get(anchor, [])
    if not hs:
        return set()
    p = hs[0]["page"]
    return set(range(max(1, p - radius), p + radius + 1))


# ---------------------------------------------------------------- basic
REPORT_KINDS = [("报告书", "环境影响报告书"), ("报告表", "环境影响报告表"), ("登记表", "环境影响登记表")]


def extract_basic(rep) -> dict:
    out = {}
    cover = " ".join(rep.page_text[:8])
    counts = {k: cover.count(s) for k, s in REPORT_KINDS}
    # 报告表文档里也可能出现"登记表"（竣工验收登记表），故仅在封面命中且数量占优时取
    kind = max(counts, key=lambda k: counts[k]) if any(counts.values()) else None
    if kind and counts[kind] > 0:
        pg = next((i for i, t in enumerate(rep.page_text[:8], 1) if REPORT_KINDS[
            [k for k, _ in REPORT_KINDS].index(kind)][1] in t), None)
        out["环评文件类型"] = Field(kind, pg, f"封面出现『{dict(REPORT_KINDS)[kind]}』", "regex")

    # 项目名称优先取**封面**（最可靠）。表格里搜"项目名称"标签很容易抓错表：
    # 临沂报告书里有一张「项目名称 | （空） | 工程内容 | 环评批复」的一期/二期情况表，
    # 按标签匹配就会把项目名抽成"工程内容"（已实测）。
    for pg in (1, 2, 3):
        lines = [l.strip() for l in rep.page_text[pg - 1].splitlines() if l.strip()]
        for i, l in enumerate(lines):
            if re.search(r"环境影响报告(书|表)", l) and i > 0:
                cand = lines[i - 1]
                if 4 <= len(cand) <= 60 and not re.search(
                        r"公示|报批稿|送审稿|建设单位|编制单位|二〇|20\d\d年|工程内容", cand):
                    out["项目名称"] = Field(
                        cand, pg, " ".join(lines[max(0, i - 2):i + 1]), "cover")
                    break
        if "项目名称" in out:
            break

    # 项目名称 / 建设单位 / 行业类别：取"名称"类的表格单元
    for t in rep.tables[:12]:
        head = t["rows"][0] if t["rows"] else []
        for row in t["rows"][:25]:
            if len(row) < 2:
                continue
            for label, key in (("项目名称", "项目名称"), ("建设项目名称", "项目名称"),
                               ("建设单位", "建设单位"), ("建设单位名称", "建设单位"),
                               ("行业类别", "行业类别"), ("建设地点", "建设地点")):
                if label in row[0] and key not in out:
                    # 取标签后**第一个非空**单元格（不能写 row[1] or row[2]：
                    # 合并单元格常见"标签 | 空 | 值"，会把隔壁列的值当项目名）
                    i0 = row.index(row[0]) if row[0] in row else 0
                    val = next((c for c in row[i0 + 1:] if c and len(_norm(c)) > 1), "")
                    if val and not re.fullmatch(r"(工程内容|项目名称|建设单位|行业类别)", _norm(val)):
                        out[key] = Field(_norm(val), t["page"], f"{row[0]}：{val}", "table")
    # 行业类别兜底：正文正则
    if "行业类别" not in out:
        for i, t in enumerate(rep.page_text[:40], 1):
            m = re.search(r"行业类别[^\n]{0,6}[：:]?\s*([^\n]{2,50})", t)
            if m and len(m.group(1)) > 2:
                out["行业类别"] = Field(_norm(m.group(1)), i, m.group(0), "regex")
                break
    # 项目名称兜底：文件名（最次，哈希名没有信息量）
    if "项目名称" not in out:
        stem = os.path.splitext(os.path.basename(rep.pdf))[0]
        stem = re.sub(r"^(公示版-|公示稿-|\d+、)", "", stem)
        out["项目名称"] = Field(stem, 1, f"文件名：{os.path.basename(rep.pdf)}", "filename")
    return out


# ---------------------------------------------------------------- materials
def extract_materials(rep, max_tables=6) -> list:
    """原辅材料表 → 物料清单（表驱动）。

    两步走，避免抓错表（实测过两种错抓）：
      1. 先按"表头列特征"筛：必须有名称类列 + 数量类列；单位列**或**数量列名里带单位均可。
      2. 再按位置收敛：若能在"原辅材料/产品方案"锚点附近找到，就只用附近的；
         否则用列特征最像的（表头含 货物名称/物料名称/原料名称 优先）。
    并排除「序号|指标名称|单位|数量」这类建设规模表（它们的"名称"列是指标名）。
    """
    EXCLUDE_NAME = ("指标名称", "项目", "工程内容", "污染物名称", "设备名称")
    pages = near_pages(rep, "原辅材料", 2) | near_pages(rep, "产品方案", 1)
    cands = []
    for t in rep.tables:
        head2 = t["rows"][0] + (t["rows"][1] if len(t["rows"]) > 1 else [])
        ci_name = _find_col(head2, NAME_COLS)
        ci_qty = _find_col(head2, QTY_COLS)
        if ci_name is None or ci_qty is None:
            continue
        name_head = head2[ci_name] if ci_name < len(head2) else ""
        if any(x in name_head for x in EXCLUDE_NAME):
            continue
        ci_unit = _find_col(head2, UNIT_COLS)
        unit_hdr = unit_from_header(head2[ci_qty] if ci_qty < len(head2) else "")
        if ci_unit is None and not unit_hdr:
            continue
        # 原辅材料表的表头通常以"名称"开头（序号后紧接名称）
        affinity = 0
        if ci_name in (0, 1):
            affinity += 1
        if re.search(r"货物名称|物料名称|原料名称|材料名称|原辅料", name_head):
            affinity += 3
        if re.search(r"消耗|用量", " ".join(head2)):
            affinity += 2
        cands.append((affinity, t["page"] in pages, t, ci_name, ci_qty, ci_unit, unit_hdr))
    if not cands:
        return []
    near = [c for c in cands if c[1]]
    pool = near or cands
    pool.sort(key=lambda c: (-c[0], c[2]["page"]))

    mats = []
    for aff, _, t, ci_name, ci_qty, ci_unit, unit_hdr in pool[:max_tables]:
        for row in t["rows"][1:]:
            if len(row) <= max(ci_name, ci_qty):
                continue
            name = _norm(row[ci_name])
            if not name or len(name) < 2 or "序号" in name or "名称" in name:
                continue
            if re.fullmatch(r"[\d.\s%\-—/]+", name):
                continue
            val, unit_hint = _num(row[ci_qty])
            unit = _norm(row[ci_unit]) if (ci_unit is not None and len(row) > ci_unit) else ""
            unit = unit or unit_hint or unit_hdr
            mats.append({"名称": name, "数量": val, "单位": unit,
                         "页码": t["page"], "原文": " | ".join(_norm(c) for c in row if c)[:200],
                         "表头": " | ".join(_norm(c) for c in t["rows"][0])[:120],
                         "method": "table"})
    seen, out = set(), []
    for m in mats:
        if m["名称"] in seen:
            continue
        seen.add(m["名称"])
        out.append(m)
    return out


# ---------------------------------------------------------------- risk materials
def extract_risk_materials(rep, max_tables=4) -> list:
    """危险物质表 → {名称, 最大贮存量t, 临界量t}。"""
    cands = tables_with_header(rep, need_name=True, need_qty=True)
    out = []
    for t in cands[:max_tables]:
        head2 = t["rows"][0] + (t["rows"][1] if len(t["rows"]) > 1 else [])
        flat = " ".join(head2)
        if "临界量" not in flat:
            continue
        ci_name = _find_col(head2, ("物质名称", "名称", "危险物质"))
        ci_q = _find_col(head2, ("最大贮存量", "最大存在量", "贮存量", "存在量", "数量"))
        ci_qc = _find_col(head2, ("临界量",))
        if ci_name is None or ci_q is None or ci_qc is None:
            continue
        for row in t["rows"][1:]:
            if len(row) <= max(ci_name, ci_q, ci_qc):
                continue
            name = _norm(row[ci_name])
            if not name or "序号" in name or len(name) < 2:
                continue
            q, _ = _num(row[ci_q])
            qc, _ = _num(row[ci_qc])
            out.append({"名称": name, "最大贮存量t": q, "临界量t": qc,
                        "页码": t["page"], "原文": " | ".join(_norm(c) for c in row if c)[:200],
                        "表头": " | ".join(_norm(c) for c in t["rows"][0])[:120],
                        "method": "table"})
    return out


# ---------------------------------------------------------------- 专项评价（报告自述）
def extract_special_stated(rep) -> dict:
    """报告自述的专项评价设置情况（污染影响类报告表：表1 专项评价设置情况）。"""
    out = {}
    pages = near_pages(rep, "专项评价设置", 1)
    for t in rep.tables:
        if pages and t["page"] not in pages:
            continue
        md = t["markdown"]
        if "专项评价" not in md:
            continue
        for row in t["rows"]:
            if len(row) < 2:
                continue
            label = _norm(row[0])
            for el in ("大气", "地表水", "地下水", "声环境", "土壤", "生态", "环境风险", "海洋"):
                if el in label and el not in out:
                    val = _norm(" ".join(c for c in row[1:] if c))
                    setflag = None
                    if re.search(r"不设置|无|不开展|/", val) and not re.search(r"设置专项|需设置", val):
                        setflag = False
                    elif re.search(r"设置", val):
                        setflag = True
                    out[el] = {"自述": val, "set": setflag, "页码": t["page"],
                               "原文": " | ".join(_norm(c) for c in row if c)[:200],
                               "method": "table"}
    return out


# ---------------------------------------------------------------- 环境保护目标
def extract_sensitive_targets(rep, max_tables=3) -> list:
    pages = near_pages(rep, "环境敏感目标", 2)
    cands = tables_with_header(rep, need_name=True, need_dist=True)
    if pages:
        cands = [t for t in cands if t["page"] in pages] or cands
    out = []
    for t in cands[:max_tables]:
        head2 = t["rows"][0] + (t["rows"][1] if len(t["rows"]) > 1 else [])
        ci_name = _find_col(head2, ("名称", "保护目标", "敏感目标", "保护对象"))
        ci_dist = _find_col(head2, DIST_COLS)
        if ci_name is None or ci_dist is None:
            continue
        for row in t["rows"][1:]:
            if len(row) <= max(ci_name, ci_dist):
                continue
            name = _norm(row[ci_name])
            if not name or "序号" in name or "名称" in name:
                continue
            d, _ = _num(row[ci_dist])
            out.append({"名称": name, "距离m": d, "原始": _norm(row[ci_dist]),
                        "页码": t["page"], "原文": " | ".join(_norm(c) for c in row if c)[:200]})
    return out[:60]


def extract_catalog_ref(rep) -> dict:
    """抽报告**自述的名录条目**——这是最有力的依据（报告自己认领的条目与情形）。

    报告表 表一有「行业类别（分类管理名录）」单元；报告书一般在"编制依据"或
    "评价工作等级"里引一句"对照《分类管理名录》，本项目属于……"。
    注意：报告可能引**旧版名录的序号**（如 2018 版把玻璃及玻璃制品编为 52，
    2021 版编为 57），所以这里只存文字，语义比对交给判据层按**条目名称与条件原文**做。
    """
    out = {}
    for t in rep.tables:
        head = " ".join(t["rows"][0]) if t["rows"] else ""
        for row in t["rows"]:
            joined = " | ".join(_norm(c) for c in row if c)
            for label, key in (("行业类别（分类管理名录）", "名录条目"),
                               ("行业类别(分类管理名录)", "名录条目"),
                               ("建设项目行业类别", "名录条目"),
                               ("行业类别", "行业类别自述"),
                               ("国民经济行业类别", "国民经济行业")):
                if label in joined and key not in out:
                    cells = [_norm(c) for c in row]
                    i = next((j for j, c in enumerate(cells) if label in c), 0)
                    val = next((c for c in cells[i + 1:] if c and len(c) > 2), "")
                    if val:
                        out[key] = Field(val, t["page"], joined[:200], "table")
    if "名录条目" not in out:
        # 报告书的自述散在正文里。**必须收紧**：全文提到《分类管理名录》的地方很多
        # （如"名录中所界定的涉及地下水的环境敏感区"），随手抓一句会把无关字词
        # 污染进名录查询串，导致匹配到别的条目（实测：常德被匹配到"农产品基地项目"）。
        # 判据：既要有「属于/归入/列入」这类声明动词，又要有「四十一、」这类章节序号。
        # 正则里**不能用 `[^。\n]`**：PDF 文本按视觉行硬换行，
# 「属于《建设项\n目环境影响评价分类管理名录》」这种跨行写法会被 \n 截断，
# 结果名录自述永远抽不到（实测：白银报告书明明是"89、生物质能发电－生活垃圾发电…应编报告书"，
# 抽取结果却是 None）。只排除句号，不排除换行。
        pats = [r"[^。]{0,40}(属于|归入|列入)[^。]{0,120}",
                r"[^。]{0,40}(对照|根据|依据)[^。]{0,20}"
                r"《建设项目环境影响评价分类管理名录》[^。]{0,120}",
                r"《分类管理名录》[^。]{0,120}"]
        section = re.compile(r"[一二三四五六七八九十]{1,3}、|\d{2,3}\s*(项|条)")
        for pat in pats:
            for h in rep.search(pat, max_hits=4, ctx=0):
                s = h["snippet"]
                if "分类管理名录" in s and section.search(s) and \
                        re.search(r"属于|归入|列入|对照|根据|依据", s):
                    out["名录条目"] = Field(s, h["page"], s, "regex")
                    break
            if "名录条目" in out:
                break
    return out


# ---------------------------------------------------------------- 名录用语映射
# 为什么需要映射：报告写"聚氨酯胶水 + 乙酸乙酯作溶剂"，名录写"年用溶剂型胶粘剂"，
# 字符串接不上。这里用**规则**做归属（可审计），规则命中不了的留给模型/人工，不硬猜。
ADHESIVE = re.compile(r"胶粘剂|胶黏剂|胶水|粘合剂|粘结剂|热熔胶|白乳胶")
COATING = re.compile(r"涂料|油漆|漆类|面漆|底漆")
SOLVENT_SUBST = ["乙酸乙酯", "乙酸丁酯", "醋酸丁酯", "甲苯", "二甲苯", "丙酮", "丁酮",
                 "环己酮", "二氯甲烷", "三氯乙烯", "四氯乙烯", "甲醇", "乙醇", "异丙醇",
                 "溶剂油", "稀释剂", "香蕉水", "天那水"]
SOLVENT_MARK = re.compile(r"溶剂型|溶剂|" + "|".join(SOLVENT_SUBST))
LOW_VOC = re.compile(r"水性|非溶剂型|低\s*VOCs?|无溶剂|粉末涂料|UV\s*涂料")


def map_to_catalog_terms(materials: list) -> dict:
    """把报告物料映射到名录用语，并按用语汇总年用量（吨）。

    返回 {用语: {"total": 值, "unit": "吨", "items": [...], "basis": 说明}}
    只做**能引证**的归属：命中规则的物料才计入；未命中的列入 unmapped。
    """
    solvent_used = {m["名称"] for m in materials
                    if any(s in (m["名称"] + m.get("原文", "")) for s in SOLVENT_SUBST)}
    buckets, unmapped = {}, []
    for m in materials:
        name = m["名称"]
        blob = name + " " + (m.get("原文") or "")
        val, unit = m.get("数量"), (m.get("单位") or "")
        if val is None:
            unmapped.append({**m, "why": "无数量"})
            continue
        cat, why = None, ""
        if ADHESIVE.search(name):
            if LOW_VOC.search(blob):
                cat, why = "非溶剂型低VOCs含量胶粘剂", "名称含胶粘剂且标注水性/低VOCs"
            elif SOLVENT_MARK.search(blob) or solvent_used:
                cat, why = "溶剂型胶粘剂", ("名称含胶粘剂且报告列出有机溶剂："
                                           + "、".join(sorted(solvent_used)) if solvent_used
                                           else "名称/原文标注溶剂型")
            else:
                unmapped.append({**m, "why": "含胶粘剂但未见溶剂型/水性标注 → 需人工或模型确认"})
                continue
        elif COATING.search(name):
            if LOW_VOC.search(blob):
                cat, why = "非溶剂型低VOCs含量涂料", "名称含涂料且标注水性/低VOCs"
            elif SOLVENT_MARK.search(blob):
                cat, why = "溶剂型涂料（含稀释剂）", "名称/原文标注溶剂型"
            else:
                unmapped.append({**m, "why": "含涂料但未见溶剂型/水性标注 → 需人工或模型确认"})
                continue
        else:
            unmapped.append({**m, "why": "不属于名录用语（胶粘剂/涂料）"})
            continue
        b = buckets.setdefault(cat, {"total": 0.0, "unit": "", "items": [], "basis": why})
        b["total"] += val
        b["unit"] = unit or b["unit"]
        b["items"].append({"名称": name, "数量": val, "单位": unit,
                           "页码": m["页码"], "原文": m.get("原文", "")})
    return {"buckets": buckets, "unmapped": unmapped, "solvent_substances": sorted(solvent_used)}


# ---------------------------------------------------------------- 判据输入的机械推导
# 每条规则给出：正则 → 结论（True/False）与可引证原文。推导不出就留空（由判据层降级为疑似）。

# 「这事没查清」的措辞 —— 命中片段含这些词就不算事实断言（见 derive_special_inputs）。
UNCERTAIN_RX = re.compile(r"无法判断|不能判断|无法确定|未抽到|未给出|待核实|需核实|"
                          r"不确定|未知|需人工确认|尚不明确|未明确")
# 疑问句形式（「是否直排？」）也不是断言。注意别误杀「是否直排：否」这种明确回答。
QUESTION_RX = re.compile(r"是否[^。\n]{0,12}(直排|排入|取水|涉及|属于)[^。\n]{0,4}[?？]")

INPUT_RULES = [
    ("厂界外500米内是否有环境空气保护目标",
     [(r"厂界外\s*500\s*m?\s*(?:范围)?内[^。\n]{0,20}(无|没有|不存在)", False),
      (r"500\s*m\s*(?:范围)?内[^。\n]{0,20}(无|没有|不存在)(环境空气)?保护目标", False),
      (r"(厂界外\s*)?500\s*m\s*(?:范围)?内有[^。\n]{0,40}(保护目标|居民|村庄|居住区)", True)]),
    # 注意顺序与否定词：True 规则排在前面，若不加否定前置断言，
    # 「废水非直排」「废水不直接排入」会先命中它并被读成"直排" —— 实测踩过
    # （生成线的草稿里写了「废水非直排（报告载明纳管/回用）」，自审却判"本项目符合
    #   地表水专项评价设置条件（新增工业废水直排）"，与判定层结论相反）。
    ("废水是否直排",
     [  # 先处理"问答式"与"后置否定"两种最常见写法，再交给通用 True 规则。
        # 为什么必须排在前面：报告表里最典型的行是「新增工业废水直排 | 否」、
        # 「是否直排：否」，否定词在短语**之后** —— 通用 True 规则只看到"废水…直排"
        # 就判成直排（本轮实测：「本项目废水是否直排：否」被判 True），
        # 而"废水直排"是**存在问题**级结论的输入，判错方向后果很重。
        (r"(废水|污水)[^。\n]{0,12}是否[^。\n]{0,10}(?:直排|排入)[^。\n]{0,6}[:：]?\s*"
         r"(?:否|不是|无|没有|未|不)", False),
        (r"(废水|污水)[^。\n]{0,20}(?:直排|直接排入|排入)[^。\n]{0,8}[:：，,、\s|]*(?:否|不是|无|没有|未)",
         False),
        (r"(废水|污水)[^。\n]{0,20}(?<!非)(?<!不)(?<!未)(?<!无)(直排|直接排入)", True),
        (r"(废水|污水)[^。\n]{0,20}(?:非|不|未|没有|无)\s*(?:直接)?(?:直排|排入)", False),
        (r"(废水|污水)[^。\n]{0,30}(不直接排放|不外排|零排放|全部回用|循环使用|纳管|回用)", False),
        (r"(废水|污水)[^。\n]{0,30}(排入|纳入|接入|接管)[^。\n]{0,20}(污水处理厂|污水厂|管网)", False)]),
    ("是否涉及集中式饮用水水源或特殊地下水资源保护区",
     [(r"不涉及[^。\n]{0,20}(饮用水水源|饮用水源|地下水资源保护区)", False),
      (r"(位于|涉及|临近)[^。\n]{0,20}(集中式饮用水水源|饮用水水源保护区|水源保护区)", True),
      (r"(矿泉水|温泉|地热水)[^。\n]{0,10}(水源|保护区|开采)", True)]),
    ("是否新增河道取水",
     [(r"不[^。\n]{0,8}(从|在)?[^。\n]{0,8}(河道|地表水|河流)[^。\n]{0,8}取水", False),
      (r"(由|从|依托)[^。\n]{0,20}(市政|自来水|自来水管网)[^。\n]{0,10}(供水|供水管网)", False),
      (r"新增[^。\n]{0,10}(河道|地表水)[^。\n]{0,6}取水", True),
      (r"取水口[^。\n]{0,20}(河道|河|地表水)", True)]),
]


def derive_special_inputs(rep) -> dict:
    """从报告原文机械推导专项评价判据的输入事实，每项带页码与可引证原文。

    **疑问/不确定守卫**（本轮新增）：命中片段若是在说"这事没查清"，就不能当成事实断言。
    实测：报告里写「废水去向未抽到（无法判断是否直排）」，True 规则读到"废水…直排"，
    于是判成"本项目新增工业废水直排"→ 直接报**存在问题**，与"缺事实只判疑似"的铁律相反。
    所以命中片段含下列措辞时**跳过该规则**，让判据层降级为"事实不足/疑似"。
    注意不能把「是否直排：否」这种明确回答也误杀 —— 那种片段没有下面的措辞、也没有问号。
    """
    out = {}
    for key, rules in INPUT_RULES:
        found = None
        for rx, val in rules:
            hits = rep.search(rx, max_hits=1, ctx=80)
            if not hits:
                continue
            h = hits[0]
            sn = h.get("snippet") or ""
            if UNCERTAIN_RX.search(sn) or QUESTION_RX.search(sn):
                continue                      # 说的是"没查清"，不是事实
            found = {"value": val, "page": h["page"], "mark": h.get("mark"),
                     "quote": sn, "method": "regex"}
            break
        out[key] = found
    return out


# 「这一页其实是废水内容」的两个特征（A3 修：防止废水表被当成废气污染物清单的来源页）
#   强：废水标准号（出现它基本可以断定这页在说废水）
#   弱：水介质专有指标（废气页里也可能顺带提一句，所以只作提示、不单独定性）
WATER_STD_RX = re.compile(r"GB\s*8978|GB\s*18918|GB\s*3544|GB\s*4287|GB\s*13458|GB\s*21900|"
                          r"GB\s*31962|GB\s*21523|DB\s*32\s*/\s*1072")
WATER_ONLY_RX = re.compile(r"COD|化学需氧量|氨氮|总磷|总氮|BOD|生化需氧量|动植物油|石油类|"
                           r"悬浮物|粪大肠菌群|阴离子表面活性剂|色度|第一类污染物")


def pollutant_terms(rep, limit_pages=6) -> dict:
    """提取废气污染物清单（用于大气专项判定）：优先污染因子/污染物排放表。

    2026-09-22 修两处（A3，用户反馈：「废气污染物清单页抽到"其中动植物油参照
    GB8987-1996 一级标准"，GB8978 是《污水综合排放标准》、动植物油是废水污染物」）：

    1. **根因**：正则里原先有一个**裸的 `氨`**，而 `finditer` 是子串匹配 ——
       废水表里的「**氨氮**」会被它命中（氨氮是常规水质指标，几乎每份报告都有），
       于是那一页（往往是含动植物油、GB8978 的**废水表**）连同摘录一起被塞进"废气污染物清单"。
       改成 `氨(?!氮)`。
    2. **用户要的那一步**：抽到的东西里如果出现**废水标准号**（GB8978/GB18918…）或
       **水介质专有污染物**（COD/氨氮/总磷/动植物油…），就记下来当"疑似抽串页"，
       由判据层挂「需人工核对」并给出页码 —— 与既有三档口径一致：宁可标需核对，不硬下结论。
       两级证据分开记（`suspect_std` 强 / `suspect_water` 弱），判据层据此决定措辞轻重。
    """
    names, pages, quotes = set(), [], []
    pat = re.compile(r"(非甲烷总烃|二噁英|氯化氢|氯气|氰化氢|氟化物|苯并\[a\]芘|"
                     r"颗粒物|二氧化硫|氮氧化物|硫化氢|氨(?!氮)|汞及其化合物|镉及其化合物|"
                     r"铅及其化合物|砷及其化合物|铬及其化合物|VOCs|挥发性有机物|甲苯|二甲苯|甲醛)")
    hits = rep.search(pat.pattern, max_hits=limit_pages, ctx=60)
    suspect_std, suspect_water = [], []
    for h in hits:
        sn = h["snippet"] or ""
        m_std = WATER_STD_RX.search(sn)
        m_water = WATER_ONLY_RX.search(sn)
        if m_std:
            suspect_std.append((h["page"], m_std.group(0)))
        elif m_water:
            suspect_water.append((h["page"], m_water.group(0)))
        for m in pat.finditer(sn):
            names.add(m.group(0))
        pages.append(h["page"])
        quotes.append(sn)
    return {"names": sorted(names), "pages": sorted(set(pages)), "quotes": quotes[:6],
            "suspect_std": suspect_std[:6], "suspect_water": suspect_water[:6]}


# 环境空气保护目标的名称特征（用于把敏感目标表里的**大气**类目标挑出来）。
# 必须与生态类目标区分：邵武报告书表里 "天然林或公益林 43m" 距离更近，
# 但它不是环境空气保护目标，拿去判大气专项会得出错误结论（已实测）。
AIR_TARGET_RX = re.compile(r"花园|小区|村|庄|居民|学校|医院|疗养|镇|社区|苑|城|府|公寓|"
                           r"宿舍|幼儿园|敬老|安置|自然村|组")
ECO_TARGET_RX = re.compile(r"天然林|公益林|保护区|湿地|河流|水库|林场|风景区|水源|"
                           r"基本农田|流域|湖泊|公园")


def derive_from_targets(rep, targets: list) -> dict:
    """用敏感目标表**机械**推导"厂界外500m内是否有环境空气保护目标"。

    为什么不交给模型：这张表有距离列，机械筛选比语义判断更准，而且天然可引证。
    """
    air = [t for t in targets
           if t.get("距离m") is not None
           and AIR_TARGET_RX.search(t.get("名称", ""))
           and not ECO_TARGET_RX.search(t.get("名称", ""))]
    if not air:
        return {}
    near = [t for t in air if t["距离m"] <= 500]
    if near:
        t = min(near, key=lambda x: x["距离m"])
        return {"厂界外500米内是否有环境空气保护目标": {
            "value": True, "page": t["页码"], "quote": t["原文"],
            "mark": None, "method": "table",
            "note": f"敏感目标表：{t['名称']} 厂界最近距离 {t['距离m']}m ≤ 500m"}}
    if len(air) >= 3:
        t = min(air, key=lambda x: x["距离m"])
        return {"厂界外500米内是否有环境空气保护目标": {
            "value": False, "page": t["页码"], "quote": t["原文"],
            "mark": None, "method": "table",
            "note": f"敏感目标表 {len(air)} 个环境空气保护目标，最近 {t['名称']} "
                    f"{t['距离m']}m > 500m"}}
    return {}


def project_digest(rep, ex, max_rows: int = 14, max_tables: int = 4) -> str:
    """项目事实卡片：把产品方案 / 原辅材料 / 建设规模表的**实际内容**摘出来，带页码。

    为什么需要它（实测教训）：直接给模型整页原文，它会引用「项目产品方案见表2-2、2-3。」
    这种**指引句**当依据 —— 页面核验能过，但依据毫无信息量，结论也就不可信。
    把表内容按「页内原样」摘出来（每行都标页码），模型才有东西可引，
    而且引出来的片段仍然真实存在于该页，核验照样成立。
    """
    lines = []
    # 只放**页面原文本身**，不加「名录条目：」这类合成前缀 ——
    # 卡片内容要能被模型直接引用当定位短语，加了前缀它照抄就核验不过（已实测）。
    for k in ("项目名称", "行业类别自述", "名录条目", "国民经济行业"):
        f = ex.basic.get(k)
        if f and f.value:
            lines.append(f"【第{f.page}页】{f.value}")
    rend = re.compile(r"产品|规格|规模|建设内容|工程内容|产量")
    for tpage, anchor in ((None, "产品方案"), (None, "原辅材料")):
        pages = near_pages(rep, anchor, 2)
        for t in rep.tables:
            if t["page"] not in pages:
                continue
            head = " | ".join(_norm(c) for c in t["rows"][0])[:100] if t["rows"] else ""
            body = []
            for r in t["rows"][1:max_rows + 1]:
                cells = [_norm(c) for c in r if _norm(c)]
                if cells:
                    body.append("  ".join(cells)[:150])
            if not body:
                continue
            if not (rend.search(head) or anchor == "原辅材料"):
                continue
            lines.append(f"【第{t['page']}页】{head}")
            lines += [f"【第{t['page']}页】{b}" for b in body]
    if ex.materials:
        lines.append("原辅材料：" + "；".join(
            f"{m['名称']} {m['数量']}{m['单位']}（P{m['页码']}）" for m in ex.materials[:20]))
    return "\n".join(lines[:120])


def extract_all(rep, verbose: bool = False) -> Extraction:
    ex = Extraction(pdf=rep.pdf)
    ex.basic = extract_basic(rep)
    ex.basic.update(extract_catalog_ref(rep))
    ex.materials = extract_materials(rep)
    ex.risk_materials = extract_risk_materials(rep)
    ex.special_stated = extract_special_stated(rep)
    ex.sensitive_targets = extract_sensitive_targets(rep)
    ex.special_inputs = derive_special_inputs(rep)
    # 表驱动推导优先：有表就机械判，模型只补表里答不了的（见表则覆盖）
    ex.special_inputs.update(derive_from_targets(rep, ex.sensitive_targets))
    pol = pollutant_terms(rep)
    ex.special_inputs["废气污染物清单"] = (
        {"value": pol["names"], "page": pol["pages"][0] if pol["pages"] else None,
         "quote": pol["quotes"][0] if pol["quotes"] else "", "method": "regex",
         "all_pages": pol["pages"],
         # 串页嫌疑随事实一起传下去，由判据层决定措辞（见 criteria.py 大气分支）
         "suspect_std": pol.get("suspect_std") or [],
         "suspect_water": pol.get("suspect_water") or []} if pol["names"] else None)
    if verbose:
        print(f"  类型={ex.basic.get('环评文件类型', Field()).value} "
              f"物料={len(ex.materials)} 风险物质={len(ex.risk_materials)} "
              f"敏感目标={len(ex.sensitive_targets)} 自述专项={len(ex.special_stated)}")
        miss = [k for k, v in ex.special_inputs.items() if not v]
        print(f"  判据输入未推导出：{miss}")
    return ex