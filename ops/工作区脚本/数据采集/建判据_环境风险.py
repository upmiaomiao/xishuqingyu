#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库数字化 (5)：HJ 169-2018 环境风险判据 → 可执行 JSON。

为什么是 HJ 169 而不是 GB 18218：
  《报告表编制技术指南（污染影响类）》表1 环境风险行注3 原文即
  「临界量及其计算方法可参考《建设项目环境风险评价技术导则》（HJ 169）附录B、附录C」，
  故临界量表取 HJ 169 附录B 表B.1（385 种）+ 表B.2（推荐值 3 类）。

产出：
  substances[]        表B.1 突发环境事件风险物质及临界量（序号/物质名称/CAS号/临界量t）
  b2_recommended[]    表B.2 其他危险物质临界量推荐值
  rules.*             表2 潜势矩阵、表C.2 P 矩阵、表1 等级矩阵、表C.1 M 评分、附录D E 分级
每条规则保留官方原行 evidence（条文是自然语言，编码是人工整理的，不吹高自动化程度）。
"""
from __future__ import annotations

import json
import os
import re
import sys

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
CRIT_DIR = os.environ.get("CRIT_DIR", os.path.join(ROOT, "判据库"))
PDF = os.environ.get("HJ169_PDF", os.path.join(CRIT_DIR, "标准文本", "HJ_169-2018.pdf"))
OUT = os.path.join(CRIT_DIR, "环境风险判据.json")

# 表B.1 所在页（0 基，含表B.2）
B_PAGES = range(16, 26)
NUM_RE = re.compile(r"^\d+(?:\.\d+)?$")
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
MARK_RE = re.compile(r"\*+\s*$")


def strip_mark(name):
    """去掉名称末尾的 * 标注（表B.1 注：该类物质按标注物质的质量计）。"""
    return MARK_RE.sub("", name or "").strip()


LINE_TOL = 6.0          # pt：同一视觉行内 y 的允许差（下标约偏 4.2~4.4 pt）
CJK = r"\u3000-\u303f\u4e00-\u9fff\uff00-\uffef"


def clean_cell(s):
    """把单元格文本规整：折叠空白，去掉中文字符之间的多余空格（换行续行的残留）。"""
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(rf"(?<=[{CJK}])\s+(?=[{CJK}])", "", s)
    return s.strip()


def spans_of(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for s in l["spans"]:
                if s["text"].strip():
                    out.append(s)
    return out


def cell_text(spans, rect):
    """按「视觉行聚类 + 行内按 x 排序」重建单元格文本。

    不能直接用 span 原始顺序：HJ 169 的 PDF 里 span 存储顺序与阅读顺序不一致，
    下标（如 CODCr 的 Cr、NH3-N 的 3）会被甩到末尾。
    """
    inside = [s for s in spans
              if rect[0] - 1 <= (s["bbox"][0] + s["bbox"][2]) / 2 <= rect[2] + 1
              and rect[1] - 1 <= (s["bbox"][1] + s["bbox"][3]) / 2 <= rect[3] + 1]
    if not inside:
        return ""
    inside.sort(key=lambda s: (s["bbox"][1] + s["bbox"][3]) / 2)
    lines, cur, cur_y = [], [], None
    for s in inside:
        y = (s["bbox"][1] + s["bbox"][3]) / 2
        if cur_y is None or y - cur_y <= LINE_TOL:
            cur.append(s)
            cur_y = y if cur_y is None else cur_y
        else:
            lines.append(cur)
            cur, cur_y = [s], y
    lines.append(cur)
    parts = []
    for ln in lines:
        ln.sort(key=lambda s: s["bbox"][0])
        parts.append("".join(s["text"] for s in ln))
    return clean_cell("".join(parts))


def rows_of(page):
    spans = spans_of(page)
    for tb in page.find_tables().tables:
        for row in tb.rows:
            # 合并单元格时 row.cells 里会出现 None
            yield ["" if c is None else cell_text(spans, c) for c in row.cells]


def parse_tables(doc):
    b1, b2 = [], []
    for i in B_PAGES:
        for row in rows_of(doc[i]):
            if len(row) < 3 or not any(row):
                continue
            head = "".join(row)
            if "序号" in head and ("物质名称" in head or "物质" in head):
                continue
            if len(row) >= 4 and NUM_RE.match(row[0]) and (CAS_RE.match(row[2]) or row[2] == "/"):
                b1.append({"no": int(float(row[0])), "name": strip_mark(row[1]),
                           "cas": None if row[2] == "/" else row[2],
                           "threshold_t": float(row[3])})
            elif len(row) >= 3 and NUM_RE.match(row[0]) and NUM_RE.match(row[2]):
                b2.append({"no": int(float(row[0])), "name": strip_mark(row[1]),
                           "threshold_t": float(row[2])})
    # 去重（同一行可能被相邻页重复检出）
    seen, u1 = set(), []
    for r in b1:
        if r["no"] in seen:
            continue
        seen.add(r["no"])
        u1.append(r)
    seen2, u2 = set(), []
    for r in b2:
        if r["no"] in seen2:
            continue
        seen2.add(r["no"])
        u2.append(r)
    u1.sort(key=lambda r: r["no"])
    u2.sort(key=lambda r: r["no"])
    return u1, u2


CRITERIA = {
    "version": "2026-09-16",
    "source": {
        "doc": "《建设项目环境风险评价技术导则》HJ 169-2018（代替 HJ/T 169-2004）",
        "issuer": "生态环境部",
        "url": "https://www.mee.gov.cn/ywgz/fgbz/bz/bzwb/other/pjjsdz/201810/t20181024_665360.shtml",
        "tables": ["表B.1 突发环境事件风险物质及临界量", "表B.2 其他危险物质临界量推荐值",
                   "表C.1 行业及生产工艺（M）", "表C.2 危险物质及工艺系统危险性等级判断（P）",
                   "表D.1~D.7 环境敏感程度（E）分级", "表2 建设项目环境风险潜势划分",
                   "表1 评价工作等级划分"],
        "note": "条文为自然语言；本 JSON 的规则由人工整理编码，evidence 保留官方原行便于审计。",
    },
    "linked_from": {
        "doc": "《建设项目环境影响报告表编制技术指南（污染影响类）》（试行）表1",
        "evidence": "有毒有害和易燃易爆危险物质存储量超过临界量3的建设项目",
        "footnote3": "临界量及其计算方法可参考《建设项目环境风险评价技术导则》（HJ 169）附录B、附录C。",
    },
    "rules": {
        "专项评价设置": {
            "element": "环境风险",
            "evidence": "有毒有害和易燃易爆危险物质存储量超过临界量3的建设项目",
            "inputs": ["危险物质清单[{名称, cas, 最大存在总量t}]"],
            "logic": "存在任一危险物质的最大存在总量 q ≥ 其临界量 Q（即单质比值 q/Q ≥ 1）",
            "gap_note": "表B.1 未列的物质按表B.2 推荐值；两者都无对应值时不得判定，应归入『存在疑似问题』",
        },
        "Q_计算": {
            "evidence": "当存在多种危险物质时，则按式（C.1）计算物质总量与其临界量比值（Q）："
                        "Q=q1/Q1+q2/Q2+…+qn/Qn",
            "note": "同一种物质在不同厂区按厂界内最大存在总量计；长输管线按两个截断阀室之间管段计",
            "grade_thresholds": [
                {"grade": "Q<1", "meaning": "环境风险潜势为Ⅰ"},
                {"grade": "1≤Q<10", "code": "Q1"},
                {"grade": "10≤Q<100", "code": "Q2"},
                {"grade": "Q≥100", "code": "Q3"},
            ],
        },
        "M_行业及生产工艺": {
            "evidence": "表C.1 行业及生产工艺（M）",
            "scores": [
                {"industry": "石化、化工、医药、轻工、化纤、有色冶炼等",
                 "items": ["涉及光气及光气化工艺、电解工艺（氯碱）、氯化工艺、硝化工艺、合成氨工艺、"
                           "裂解（裂化）工艺、氟化工艺、加氢工艺、重氮化工艺、氧化工艺、过氧化工艺、"
                           "胺基化工艺、磺化工艺、聚合工艺、烷基化工艺、新型煤化工工艺、电石生产工艺、"
                           "偶氮化工艺"], "score": "10/套"},
                {"industry": "石化、化工、医药、轻工、化纤、有色冶炼等",
                 "items": ["无机酸制酸工艺、焦化工艺"], "score": "5/套"},
                {"industry": "石化、化工、医药、轻工、化纤、有色冶炼等",
                 "items": ["其他高温或高压，且涉及危险物质的工艺过程、危险物质贮存罐区"],
                 "score": "5/套（罐区）",
                 "note": "高温指工艺温度≥300 ℃，高压指压力容器的设计压力≥10.0 MPa"},
                {"industry": "管道、港口/码头等",
                 "items": ["涉及危险物质管道运输项目、港口/码头等"], "score": "10"},
                {"industry": "石油天然气",
                 "items": ["石油、天然气、页岩气开采（含净化），气库（不含加气站的气库），"
                           "油库（不含加气站的油库）、油气管线（不含城镇燃气管线）"], "score": "10"},
                {"industry": "其他", "items": ["涉及危险物质使用、贮存的项目"], "score": "5"},
            ],
            "grades": [
                {"code": "M1", "condition": "M>20"},
                {"code": "M2", "condition": "10<M≤20"},
                {"code": "M3", "condition": "5<M≤10"},
                {"code": "M4", "condition": "M=5"},
            ],
            "multi_unit_note": "具有多套工艺单元的项目，对每套生产工艺分别评分并求和",
        },
        "P_危险性分级": {
            "evidence": "表C.2 危险物质及工艺系统危险性等级判断（P）",
            "matrix": {
                "rows": ["Q≥100", "10≤Q<100", "1≤Q<10"],
                "cols": ["M1", "M2", "M3", "M4"],
                "values": [["P1", "P1", "P2", "P3"],
                           ["P1", "P2", "P3", "P4"],
                           ["P2", "P3", "P4", "P4"]],
            },
        },
        "E_环境敏感程度": {
            "evidence": "附录D 环境敏感程度（E）的分级",
            "大气": {
                "table": "表D.1 大气环境敏感程度分级",
                "levels": [
                    {"code": "E1", "condition": "周边5 km 范围内居住区、医疗卫生、文化教育、科研、行政办公等"
                                                "机构人口总数大于5 万人，或其他需要特殊保护区域；"
                                                "或周边500 m 范围内人口总数大于1000 人；"
                                                "油气、化学品输送管线管段周边200 m 范围内，每千米管段人口数大于200 人"},
                    {"code": "E2", "condition": "周边5 km 范围内上述机构人口总数大于1 万人、小于5 万人；"
                                                "或周边500 m 范围内人口总数大于500 人、小于1000 人；"
                                                "管线管段周边200 m 范围内每千米人口数大于100 人、小于200 人"},
                    {"code": "E3", "condition": "周边5 km 范围内上述机构人口总数小于1 万人；"
                                                "或周边500 m 范围内人口总数小于500 人；"
                                                "管线管段周边200 m 范围内每千米人口数小于100 人"},
                ],
            },
            "地表水": {"table": "表D.2~D.4 地表水环境敏感程度分级",
                       "note": "由受纳水体功能敏感性（F1/F2/F3）与下游环境敏感目标（S1/S2/S3）组合确定，"
                               "分级矩阵见表D.2，需按报告自述的水体功能与敏感目标取值"},
            "地下水": {"table": "表D.5~D.7 地下水环境敏感程度分级",
                       "note": "由包气带防污性能（D1/D2/D3）、含水层易污染特征（F1/F2/F3）与"
                               "地下水环境敏感程度（G1/G2/G3）组合确定，分级矩阵见表D.5"},
        },
        "潜势划分": {
            "evidence": "表2 建设项目环境风险潜势划分",
            "matrix": {
                "rows": ["E1", "E2", "E3"],
                "cols": ["P1", "P2", "P3", "P4"],
                "values": [["Ⅳ+", "Ⅳ", "Ⅲ", "Ⅲ"],
                           ["Ⅳ", "Ⅲ", "Ⅲ", "Ⅱ"],
                           ["Ⅲ", "Ⅲ", "Ⅱ", "Ⅰ"]],
            },
            "note": "Ⅳ+为极高环境风险；当 Q<1 时潜势直接为Ⅰ（表2 之外的前置规则，见 C.1.1）",
        },
        "评价工作等级": {
            "evidence": "表1 评价工作等级划分",
            "mapping": {"Ⅳ、Ⅳ+": "一级", "Ⅲ": "二级", "Ⅱ": "三级", "Ⅰ": "简单分析"},
            "note": "风险潜势为Ⅳ及以上进行一级评价；Ⅲ二级；Ⅱ三级；Ⅰ可开展简单分析（见附录A）",
            "scope": {
                "大气": "一级、二级评价范围距项目边界一般不低于5 km；三级不低于3 km",
                "地表水": "参照 HJ 2.3 确定",
                "地下水": "参照 HJ 610 确定",
            },
        },
    },
}


def main():
    if not os.path.exists(PDF):
        sys.exit(f"缺少 PDF：{PDF}")
    d = fitz.open(PDF)
    b1, b2 = parse_tables(d)
    d.close()

    data = dict(CRITERIA)
    data["substances"] = b1
    data["b2_recommended"] = b2
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    print(f"表B.1 物质 {len(b1)} 种；表B.2 推荐值 {len(b2)} 类 → {OUT}")
    print(f"  序号范围 {b1[0]['no']}~{b1[-1]['no']}（连续性检查："
          f"{'连续' if [r['no'] for r in b1] == list(range(1, len(b1) + 1)) else '不连续'}）")
    print(f"  临界量取值范围 {min(r['threshold_t'] for r in b1)}~"
          f"{max(r['threshold_t'] for r in b1)} t")
    print(f"  示例：{b1[0]} … {b1[-1]}")

    # ==== 机械判定自检（矩阵往返） ====
    print("\n===== 矩阵自检 =====")
    m = data["rules"]["P_危险性分级"]["matrix"]
    for q, row in zip(m["rows"], m["values"]):
        print(f"  Q {q:10s} → " + "  ".join(f"{c}:{v}" for c, v in zip(m["cols"], row)))
    m2 = data["rules"]["潜势划分"]["matrix"]
    for e, row in zip(m2["rows"], m2["values"]):
        print(f"  {e} → " + "  ".join(f"{c}:{v}" for c, v in zip(m2["cols"], row)))
    print(f"  等级映射 {data['rules']['评价工作等级']['mapping']}")


if __name__ == "__main__":
    sys.exit(main())