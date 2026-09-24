#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把《报告表编制技术指南（污染影响类）试行》的"具体编制要求"转成结构化模板。

为什么要有这一步：报告生成智能体需要一个"应含哪些章节、每节必须写哪些字段"的清单。
这个清单**不能由人凭印象手打**（本项目在判据上已吃过一次亏），必须从指南正文机械导出，
每条都带指南页码，可复查。

做法：
  ① 解析指南 PDF（9 页）→ 定位 （一）…（七）各节及其页码；
  ② 用"字段名：说明"句式切出每节要求的字段，说明一并保留；
  ③ 用**真实报告表**（生物质环评.pdf，216 页）的章节树反向核对"指南节 ↔ 实际章节"一一对应，
     把核对结果写进产物，作为"这份模板没编"的证据；
  ④ 额外字段（本工具自己加的"由谁产出"归类）单独放在 `本工具归类` 下，与指南原文严格分开 ——
     指南说的和我们的判断不能混为一谈。

产物：判据库/报告表结构.json
用法：python 建判据_报告表结构.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # _脚本代码/
WORK = os.path.dirname(ROOT)                       # 0911训练/
sys.path.insert(0, os.path.join(ROOT, "审核智能体"))   # 复用解析层

from audit.parse import load_or_parse  # noqa: E402

CRIT = os.path.join(WORK, "判据库")
GUIDE = os.path.join(CRIT, "报告表编制技术指南（污染影响类）试行.pdf")
REAL = os.path.join(WORK, "环评报告", "环评报告", "环评报告", "生物质环评.pdf")
OUT = os.path.join(CRIT, "报告表结构.json")
CACHE = os.path.join(ROOT, "审核智能体", "_cache")

SEC_RX = re.compile(r"（([一二三四五六七八九十]+)）([\u4e00-\u9fff、，]{2,26})")
FIELD_RX = re.compile(r"(?:^|[\s。；，])([\u4e00-\u9fff（）()A-Za-z0-9m²、]{2,18}?)：")

# 本工具自己的归类：每节内容"由谁产出"。这是**我们的工程判断**，不是指南要求，
# 所以单独存放。四种产出方式：
#   填报      —— 必须由使用者填写，工具不猜
#   代码判定  —— 由判据库＋项目信息推算（可追溯）
#   模型撰写  —— 允许模型写，但数字必须来自填报/判据库
#   需资料    —— 必须有人提供原始资料（监测/踏勘/图件），工具只留占位并标注
PLAN = {
    "建设项目基本情况": {
        "建设项目名称": "填报", "项目代码": "填报", "建设地点": "填报", "地理坐标": "填报",
        "国民经济行业类别": "填报", "建设项目行业类别": "填报", "是否开工建设": "填报",
        "用地（用海）面积（m2）": "填报",
        "专项评价设置情况": "代码判定",
        "规划情况": "填报", "规划环境影响评价情况": "填报",
        "规划及规划环境影响评价符合性分析": "模型撰写", "其他符合性分析": "模型撰写",
    },
    "建设项目工程分析": {
        "建设内容": "填报", "工艺流程和产排污环节": "填报",
        "与项目有关的原有环境污染问题": "需资料",
    },
    "区域环境质量现状、环境保护目标及评价标准": {
        "区域环境质量现状": "需资料", "环境保护目标": "填报",
        "污染物排放控制标准": "代码判定", "总量控制指标": "填报",
    },
    "主要环境影响和保护措施": {
        "施工期环境保护措施": "模型撰写", "运营期环境影响和保护措施": "模型撰写",
    },
    "环境保护措施监督检查清单": {"按要素填写": "模型撰写"},
    "结论": {"从环境保护角度，明确建设项目环境影响可行或不可行的结论": "代码判定"},
}

# 章节与"表N"的对应（报告表格式）；由真实报告表核对得出，见产物里的 章节核对
SECNO = {"一": "表一", "二": "表二", "三": "表三", "四": "表四", "五": "表五", "六": "表六", "七": "附表"}


def clean(name: str) -> str:
    n = re.sub(r"\s+", "", name)
    n = n.replace("m2", "m²")
    return n


def main():
    if not os.path.isfile(GUIDE):
        print("找不到指南：", GUIDE)
        return 1
    G = load_or_parse(GUIDE, cache_dir=CACHE)
    pages = [re.sub(r"\s+", " ", t).strip() for t in G.page_text]
    body = " ".join(pages)
    start = body.find("（一）")
    tail = body[start:] if start >= 0 else body

    # ① 定位各节与页码
    secs = []
    for m in SEC_RX.finditer(tail):
        no, name = m.group(1), clean(m.group(2))
        # 该节正文在 body 中的位置 → 推页码
        pos = start + m.start()
        acc, page = 0, 1
        for i, p in enumerate(pages, 1):
            acc += len(p) + 1
            if acc > pos:
                page = i
                break
        secs.append({"序号": "（%s）" % no, "名称": name, "指南页码": page, "位置": m.start()})
    # 去重（同名只留第一次）
    uniq, seen = [], set()
    for s in secs:
        if s["名称"] in seen:
            continue
        seen.add(s["名称"])
        uniq.append(s)
    secs = uniq

    # ② 每节切字段（字段名＋说明），边界是下一节的起点
    for i, s in enumerate(secs):
        end = secs[i + 1]["位置"] if i + 1 < len(secs) else len(tail)
        chunk = tail[s["位置"]:end]
        fields, hits = [], list(FIELD_RX.finditer(chunk))
        for j, m in enumerate(hits):
            name = clean(m.group(1))
            if re.fullmatch(r"[0-9）()、]+", name) or len(name) < 2:
                continue
            desc_end = hits[j + 1].start() if j + 1 < len(hits) else len(chunk)
            desc = re.sub(r"\s+", "", chunk[m.end():desc_end])
            if fields and fields[-1]["字段"] == name:
                continue
            fields.append({"字段": name, "指南说明": desc[:300]})
        s["字段"] = fields
        s.pop("位置", None)

    # ③ 用真实报告表核对章节对应
    check = {"文件": os.path.basename(REAL), "存在": os.path.isfile(REAL)}
    if check["存在"]:
        R = load_or_parse(REAL, cache_dir=CACHE)
        l1 = [c["title"].strip() for c in R.toc if c.get("level") == 1]
        check["页数"] = R.pages
        check["表格数"] = len(R.tables)
        check["真实一级章节"] = l1[:12]
        # 指南节名 vs 真实章节：真实章节形如"三、区域环境质量现状、环境保护目标及评价标准"
        pairs = []
        for s in secs:
            hit = next((x for x in l1 if s["名称"] and s["名称"] in x.replace(" ", "")), None)
            pairs.append({"指南节": s["名称"], "真实章节": hit, "一致": bool(hit)})
        check["逐节核对"] = pairs
        check["全部一致"] = all(p["一致"] for p in pairs if p["指南节"] != "其他要求")

    # ④ 汇总表1 的关键注（专项评价数量上限等），已在别的判据里，这里只引用不重复
    out = {
        "来源": os.path.basename(GUIDE),
        "文件类型": "建设项目环境影响报告表（污染影响类）",
        "章节": [{"序号": s["序号"], "名称": s["名称"], "表": SECNO.get(s["序号"][1:-1], ""),
                  "指南页码": s["指南页码"], "字段": s["字段"]} for s in secs],
        "章节核对": check,
        "本工具归类": PLAN,
        "归类说明": "「指南页码/字段/指南说明」来自指南原文，机械导出；"
                    "「本工具归类」是本项目自己判断的产出方式（填报/代码判定/模型撰写/需资料），"
                    "不是指南要求，二者不可混用。",
        "生成": {"脚本": os.path.basename(__file__), "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print("已写出：", OUT)
    print("章节 %d 个，字段合计 %d 个" % (len(out["章节"]), sum(len(s["字段"]) for s in out["章节"])))
    for s in out["章节"]:
        print("  %-4s %-6s P%-2s %-30s 字段 %d" % (s["序号"], s["表"], s["指南页码"], s["名称"][:28], len(s["字段"])))
    if check.get("存在"):
        print("真实报告表核对（%s，%s 页）：全部一致=%s"
              % (check["文件"], check.get("页数"), check.get("全部一致")))
        for p in check["逐节核对"]:
            print("    %-30s → %s" % (p["指南节"][:28], p["真实章节"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())