#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把环评报告 md 转成带 frontmatter 的 OKF 格式。

输入：一目录的原始 md（如 /data/fagui_rag/eia_reports_raw）
输出：<bundle>/环评报告/<名称>.md，frontmatter 字段与既有语料保持一致
     （type / title / description / tags / status / region / source_path …）

刻意不做的事：不改正文内容、不切块、不重排章节 —— 正文原样保留，
只加抬头元数据，便于问题定位与过滤；检索效果由样本验证来判定。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter

PROVINCES = [
    "北京", "天津", "河北", "山西", "内蒙古", "辽宁", "吉林", "黑龙江", "上海", "江苏",
    "浙江", "安徽", "福建", "江西", "山东", "河南", "湖北", "湖南", "广东", "广西",
    "海南", "重庆", "四川", "贵州", "云南", "西藏", "陕西", "甘肃", "青海", "宁夏",
    "新疆", "台湾", "香港", "澳门",
]
INDUSTRY_KW = [
    "生活垃圾焚烧", "垃圾焚烧", "焚烧", "固废", "危险废物", "危废", "填埋", "污泥",
    "渗滤液", "医疗废物", "污水处理", "再生水", "供水", "管网", "泵站",
    "公路", "铁路", "城市轨道", "地铁", "桥梁", "隧道", "港口", "航道",
    "输变电", "变电站", "输电", "风电", "光伏", "储能", "核电", "火电", "热电",
    "天然气", "管道", "石油", "化工", "制药", "钢铁", "水泥", "有色", "造纸",
    "电池", "半导体", "电子", "汽车", "机械", "食品", "纺织", "建材", "矿山",
    "采掘", "煤炭", "稀土", "表面处理", "电镀", "铸造", "涂装", "养殖", "屠宰",
]
TITLE_HINT = re.compile(r"(环境影响报告书|环境影响报告表|环境影响评价报告|环评报告)")
NAME_PAT = re.compile(r"项目名称[：:]\s*([^\s|，。；]{2,40})")
BUILDER_PAT = re.compile(r"建设单位[：:]\s*([^\s|，。；]{2,40})")
MAKER_PAT = re.compile(r"(?:编制单位|环评单位|评价单位)[：:]\s*([^\s|，。；]{2,40})")
INDUSTRY_PAT = re.compile(r"行业类别[：:]?\s*([^\s|，。；]{2,40})")


def clean_name(s: str) -> str:
    s = re.sub(r"[\\/:*?\"<>|\n\r\t]+", " ", s or "")
    s = re.sub(r"\s{2,}", " ", s).strip(" .-_")
    return s[:120]


def pick_title(stem: str, head: str) -> str:
    m = NAME_PAT.search(head)
    if m:
        return clean_name(m.group(1))
    # 前 20 行里找像标题的行
    for ln in head.splitlines()[:20]:
        t = ln.strip().lstrip("#").strip()
        t = re.sub(r"[*_`]+", "", t)
        if 6 <= len(t) <= 60 and TITLE_HINT.search(t):
            return clean_name(t)
    for ln in head.splitlines()[:8]:
        t = ln.strip().lstrip("#").strip()
        t = re.sub(r"[*_`]+", "", t)
        if 6 <= len(t) <= 60 and not t.startswith(("目", "第", "1", "2")):
            return clean_name(t)
    return clean_name(stem)


def detect_region(text: str) -> str:
    for p in PROVINCES:
        if p in text:
            return p
    return ""


def detect_industries(text: str):
    out = []
    for kw in INDUSTRY_KW:
        if kw in text:
            out.append(kw)
        if len(out) >= 3:
            break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/data/fagui_rag/eia_reports_raw")
    ap.add_argument("--bundle", default="/data/fagui_rag/okf_bundles")
    ap.add_argument("--corpus", default="环评报告")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--min-bytes", type=int, default=2000)
    a = ap.parse_args()

    out_dir = os.path.join(a.bundle, a.corpus)
    os.makedirs(out_dir, exist_ok=True)

    files = sorted(f for f in os.listdir(a.src) if f.lower().endswith(".md"))
    if a.limit:
        files = files[: a.limit]
    print(f"待转换 {len(files)} 份（源目录 {a.src}）")

    stat = Counter()
    rows = []
    for fn in files:
        sp = os.path.join(a.src, fn)
        size = os.path.getsize(sp)
        if size < a.min_bytes:
            stat["跳过：过小/空文件"] += 1
            continue
        try:
            body = open(sp, encoding="utf-8", errors="replace").read()
        except Exception:
            stat["跳过：读取失败"] += 1
            continue
        head = body[:4000]
        stem = os.path.splitext(fn)[0]
        title = pick_title(stem, head)
        region = detect_region(head) or detect_region(stem)
        inds = detect_industries(stem + head[:1500])
        builder = BUILDER_PAT.search(head)
        maker = MAKER_PAT.search(head)
        industry = INDUSTRY_PAT.search(head)

        tags = ["环评报告", "环境影响评价", "建设项目"]
        if region:
            tags.append(region)
        tags += inds

        rel = f"{a.corpus}/{clean_name(stem)}.md"
        lines = [
            "---",
            "type: report",
            f"title: {title}",
            f"description: 环境影响报告（{'/'.join(inds) if inds else '建设项目'}）：{title}",
            "tags:",
            *[f"- {t}" for t in dict.fromkeys(tags)],
            "status: 已公开",
            "region_type: 地方" if region else "region_type: 国家",
            f"region: {region or '全国'}",
            "doc_role: 环境影响报告书",
        ]
        if builder:
            lines.append(f"建设单位: {clean_name(builder.group(1))}")
        if maker:
            lines.append(f"编制单位: {clean_name(maker.group(1))}")
        if industry:
            lines.append(f"行业类别: {clean_name(industry.group(1))}")
        lines.append(f"source_path: {rel}")
        lines.append("---")
        text = "\n".join(lines) + "\n\n" + f"# {title}\n\n" + body.lstrip()

        dest = os.path.join(out_dir, clean_name(stem) + ".md")
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)
        stat["已转换"] += 1
        rows.append((len(body), title, region, inds, os.path.basename(dest)))

    print("\n结果：")
    for k, v in stat.items():
        print(f"  {k}: {v}")
    print(f"  输出目录 {out_dir}  体积 "
          f"{sum(os.path.getsize(os.path.join(out_dir, r[4])) for r in rows)/1024/1024:.1f} MB")
    print("\n抽样（前 8 份）:")
    for chars, title, region, inds, dest in rows[:8]:
        print(f"  {chars:9,d} 字  [{region or '—'}] {title[:34]}  {inds}")
    print("\n字段覆盖：")
    cov = Counter()
    for _, title, region, inds, _d in rows:
        cov["有省份"] += 1 if region else 0
        cov["有行业"] += 1 if inds else 0
    print(f"  {dict(cov)} / {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
