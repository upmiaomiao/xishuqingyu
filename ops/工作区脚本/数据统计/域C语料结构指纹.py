"""域 C（法规与监管执法）语料结构指纹扫描。

用途
    Phase 0 的第一步：用统计手段回答「这批材料里真实存在什么结构」，
    为候选 Task Form 的 Evidence Requirement 设计提供数据依据，
    避免重演旧系统「先写 59 个 Spec，再发现 43 个结构上产不出数据」的失败。

输入（只读）
    生态环境法律法规/         307 部（法律/行政法规/规章）
    生态环境标准规范/         2814 项
    生态环境监管执法/类案法条推荐/现有系统案例库/    72 份「XX类案件学习要点」
    生态环境监管执法/类案法条推荐/督察管理/          454 份督察通报
    生态环境监管执法/异常问题核查/                   3 份流程 docx + 1 份 xls

输出
    UTF-8 Markdown 报告，默认写到
    _工作记录/方案设计/域C-语料结构指纹数据.md
    （脚本自身不修改任何原始数据）

运行
    python _脚本代码/数据统计/域C语料结构指纹.py
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
OUT = WORKSPACE / "_工作记录/方案设计/域C-语料结构指纹数据.md"

# ── 结构标记 ───────────────────────────────────────────────
MD_HEADER = re.compile(r"^#{1,6}\s*(\S.*?)\s*$", re.M)
CN_SECTION = re.compile(r"^[　\s]*([一二三四五六七八九十]+)[、．.]\s*(\S.*?)\s*$", re.M)
CN_ARTICLE = re.compile(r"第([一二三四五六七八九十百零〇\d]+)条")
LAW_CITE = re.compile(r"《([^》]{2,40})》\s*(?:第([一二三四五六七八九十百零〇\d]+)条)?")
NUM_UNIT = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg/L|mg/m3|mg/m³|μg/m3|µg/m3|%|℃|°C|倍|吨|t/d|吨/日|万t|亿元|万元|dB)")
FULL_DATE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
CIRCULAR = re.compile(r"第(\d{4})号")
ENACT = re.compile(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起(?:施行|实施)")

# 领域结构特征词：判断材料能否支撑某类证明链
FEATURES: dict[str, re.Pattern[str]] = {
    "法律责任章": re.compile(r"法律责任|罚\s*则|处罚"),
    "章结构": re.compile(r"^#{1,6}\s*第[一二三四五六七八九十]+章", re.M),
    "法条引用": LAW_CITE,
    "案情简介": re.compile(r"案情简介|案情概述|基本案情"),
    "查处情况": re.compile(r"查处情况|处理情况|处理结果|处罚结果"),
    "启示意义": re.compile(r"启示意义|典型意义|案例启示|指导意义"),
    "法律规定及罚则": re.compile(r"法律规定及?罚则|法律依据|相关规定"),
    "有关情况": re.compile(r"有关情况|基本情况|背景情况"),
    "存在问题": re.compile(r"存在问题|主要问题|发现问题"),
    "原因分析": re.compile(r"原因分析|问题原因"),
    "失职失责": re.compile(r"失职失责|履职不到位|监管不力|敷衍应对|推进不力"),
    "整改要求": re.compile(r"整改|整治|销号|回头看"),
    "监测数值": NUM_UNIT,
    "完整日期": FULL_DATE,
    "排放限值": re.compile(r"排放限值|限值|排放标准|浓度限值"),
    "监测方法": re.compile(r"测定|监测方法|分光光度法|色谱"),
    "强制性条文": re.compile(r"强制性条文|必须严格执行"),
    "罚则金额": re.compile(r"罚款|处以|处罚款|没收"),
    "要件要素": re.compile(r"构成要件|适用条件|前置条件|违法事实"),
    "主体身份": re.compile(r"排污单位|建设单位|生产经营者|当事人|企业事业单位"),
    "许可": re.compile(r"排污许可|许可证|环评批复|审批"),
}

CORPORA = [
    ("法规·法律",     WORKSPACE / "生态环境法律法规/法律"),
    ("法规·行政法规", WORKSPACE / "生态环境法律法规/行政法规"),
    ("法规·规章",     WORKSPACE / "生态环境法律法规/规章"),
    ("标准规范",      WORKSPACE / "生态环境标准规范"),
    ("类案学习要点",  WORKSPACE / "生态环境监管执法/类案法条推荐/现有系统案例库"),
    ("督察通报",      WORKSPACE / "生态环境监管执法/类案法条推荐/督察管理"),
]

SAMPLE_CAP = 260


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan(label: str, root: Path) -> dict:
    files = sorted(root.rglob("*.md")) if root.exists() else []
    picked = files if len(files) <= SAMPLE_CAP else files[:SAMPLE_CAP]
    feat_hits: Counter[str] = Counter()
    headers: Counter[str] = Counter()
    sections: Counter[str] = Counter()
    cites: Counter[str] = Counter()
    art_counts: list[int] = []

    for f in picked:
        text = read_text(f)
        for name, pat in FEATURES.items():
            if pat.search(text):
                feat_hits[name] += 1
        for m in MD_HEADER.finditer(text):
            h = m.group(1).strip().rstrip("　 ")
            if 0 < len(h) <= 30:
                headers[h] += 1
        for m in CN_SECTION.finditer(text):
            s = m.group(2).strip()
            if 0 < len(s) <= 24:
                sections[s] += 1
        for m in LAW_CITE.finditer(text):
            cites[m.group(1)] += 1
        art_counts.append(len(CN_ARTICLE.findall(text)))

    n = len(picked) or 1
    art_counts.sort()
    return {
        "label": label, "total": len(files), "picked": len(picked),
        "feat_hits": feat_hits, "headers": headers, "sections": sections,
        "cites": cites, "art_median": art_counts[len(art_counts) // 2] if art_counts else 0,
        "art_max": art_counts[-1] if art_counts else 0,
        "art_zero": sum(1 for c in art_counts if c == 0),
        "n": n,
    }


def main() -> None:
    results = [scan(label, root) for label, root in CORPORA]

    lines: list[str] = []
    lines.append("# 域 C 语料结构指纹数据")
    lines.append("")
    lines.append(f"> 由 `_脚本代码/数据统计/域C语料结构指纹.py` 生成，"
                 f"生成时间 {datetime.now():%Y-%m-%d %H:%M}")
    lines.append(f"> 每类抽样上限 {SAMPLE_CAP} 篇；判据为结构标记的出现文档数占比。")
    lines.append("")

    # ── 特征覆盖矩阵 ──
    lines.append("## 1. 结构特征覆盖矩阵（占该类的百分比）")
    lines.append("")
    order = list(FEATURES.keys())
    lines.append("| 特征 | " + " | ".join(r["label"] for r in results) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in results) + " |")
    for feat in order:
        cells = []
        for r in results:
            pct = 100.0 * r["feat_hits"][feat] / r["n"]
            cells.append(f"{pct:.0f}%" if r["feat_hits"][feat] else "·")
        lines.append(f"| {feat} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("> `·` = 抽样中无一篇命中。")
    lines.append("")

    # ── 规模 ──
    lines.append("## 2. 规模与条文切分性")
    lines.append("")
    lines.append("| 语料 | 全库篇数 | 抽样 | 「第X条」中位数 | 最大 | 无条文的篇数 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for r in results:
        lines.append(f"| {r['label']} | {r['total']} | {r['picked']} | "
                     f"{r['art_median']} | {r['art_max']} | {r['art_zero']} |")
    lines.append("")

    # ── 章节标题模式 ──
    lines.append("## 3. 出现频次最高的章节标题 / 中文序号小标题（Top 15）")
    lines.append("")
    for r in results:
        lines.append(f"### {r['label']}")
        lines.append("")
        lines.append("Markdown 标题：")
        top = [h for h, _ in r["headers"].most_common(15)]
        lines.append("· " + "　/　".join(top) if top else "（无）")
        lines.append("")
        lines.append("中文序号小标题：")
        top2 = [h for h, _ in r["sections"].most_common(15)]
        lines.append("· " + "　/　".join(top2) if top2 else "（无）")
        lines.append("")

    # ── 被引法规 ──
    lines.append("## 4. 出现频次最高的被引法规（Top 20）")
    lines.append("")
    for r in results:
        if not r["cites"]:
            continue
        lines.append(f"**{r['label']}**：" + "；".join(
            f"{name}({cnt})" for name, cnt in r["cites"].most_common(20)))
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {OUT}")
    print(f"lines: {len(lines)}")
    for r in results:
        print(f"  {r['label']}: total={r['total']} picked={r['picked']}")


if __name__ == "__main__":
    main()
