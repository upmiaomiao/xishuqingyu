#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库数字化 (2)：分类管理名录 docx 表 → 结构化 JSON + 案例验证。

表结构：| 序号 | 项目类别 | 报告书条件 | 报告表条件 | 登记表条件 | 环境敏感区含义 |
单格行（"一、农业01、林业02"）是行业大类分节；其余为条目。

产出 JSON 字段：
  section     行业大类
  no          序号
  category    项目类别
  report_book / report_form / registry   三档条件（"/" 表示该档不适用）
  sensitive   本栏目环境敏感区含义
"""
from __future__ import annotations

import json
import re
import sys

sys.path.insert(0, "/tmp")
from importlib import import_module

docx = import_module("抽docx")

DOCX = "/data/fagui_rag/criteria/分类管理名录2021.docx"
OUT = "/data/fagui_rag/criteria/分类管理名录2021.json"

SECTION_RE = re.compile(r"^[一二三四五六七八九十百]+、")
NUM_RE = re.compile(r"^\s*(\d{1,3})\s*$")


def norm(s: str) -> str:
    s = re.sub(r"\s+", " ", s or "").strip()
    return s


def parse():
    items = docx.parse_docx(DOCX)
    tables = [c for k, c in items if k == "table"]
    if not tables:
        raise SystemExit("docx 里没找到表格")
    rows = tables[0]

    out, section, cur = [], "", None
    for r in rows:
        cells = [norm(c) for c in r]
        # 补齐到 6 列
        while len(cells) < 6:
            cells.append("")
        joined = " ".join(c for c in cells if c)
        if not joined:
            continue
        nonempty = [c for c in cells if c]
        # 表头
        if "环评类别" in cells[0] or cells[0].startswith("环评类别"):
            continue
        # 分节行：只有一个非空格，且以"一、"开头
        if len(nonempty) == 1 and SECTION_RE.match(nonempty[0]):
            section = nonempty[0]
            continue
        no_m = NUM_RE.match(cells[0])
        if not no_m:
            # 可能是续行（项目类别换行），并入上一条
            if cur and joined and not SECTION_RE.match(joined):
                cur["category"] = (cur["category"] + " " + joined).strip()
            continue
        cur = {
            "section": section,
            "no": int(no_m.group(1)),
            "category": cells[1],
            "report_book": cells[2],
            "report_form": cells[3],
            "registry": cells[4],
            "sensitive": cells[5],
        }
        out.append(cur)
    return out


def main():
    data = parse()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    secs = sorted({d["section"] for d in data if d["section"]})
    print(f"条目 {len(data)} 条，行业大类 {len(secs)} 个 → {OUT}")
    rb = sum(1 for d in data if d["report_book"] not in ("/", ""))
    rf = sum(1 for d in data if d["report_form"] not in ("/", ""))
    rg = sum(1 for d in data if d["registry"] not in ("/", ""))
    print(f"  有报告书条件 {rb} 条，有报告表条件 {rf} 条，有登记表条件 {rg} 条")
    print(f"  前 4 个大类: {secs[:4]}")

    # ==== 案例验证：截图那条意见 ====
    # 项目：聚氨酯胶水 12 t/a，乙酸乙酯作溶剂，工艺含搅拌/涂底/干燥并产生非甲烷总烃
    # 名录判据：'年用溶剂型胶粘剂10吨及以上的' → 应编报告书
    print("\n===== 案例验证：检索含'胶粘剂'的条目 =====")
    hits = [d for d in data if "胶粘剂" in d["category"] or "胶粘剂" in d["report_book"]
            or "胶粘剂" in d["report_form"]]
    for d in hits:
        print(f"\n[{d['section']}] 序号{d['no']}  {d['category'][:60]}")
        print(f"   报告书: {d['report_book'][:120]}")
        print(f"   报告表: {d['report_form'][:120]}")
        print(f"   登记表: {d['registry'][:60]}")

    print("\n===== 判据机械判定（模拟审核项的判据层） =====")
    for d in hits:
        if re.search(r"溶剂型胶粘剂\s*(\d+)\s*吨", d["report_book"]):
            m = re.search(r"溶剂型胶粘剂\s*(\d+)\s*吨", d["report_book"])
            thr = int(m.group(1))
            used = 12
            verdict = "应编报告书" if used >= thr else "阈值未达"
            print(f"  序号{d['no']}：阈值 {thr} 吨，项目用量 {used} 吨 → {verdict}"
                  f"（{'与实际编报告表不符 → 存在问题' if used >= thr else ''}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
