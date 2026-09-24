"""域 C 候选 Task Form 的语料覆盖率估算（Phase 0 核心产出）。

设计原则
    旧系统的核心失败是「先写 59 个 Spec，再发现 43 个结构上产不出数据」。
    本脚本反过来：先为每个候选 Form 定义 **Evidence Requirement 的可判定代理**，
    再回到真实语料上统计「这个 Form 能吃掉多少篇材料」，只有过线的 Form 才进 Registry。

判据说明
    每个 Form 的 coverage 判据都写成对 FileRecord 的结构测试，只看材料里
    **是否真实存在该 Form 所需的证据要素**，不调用任何模型、不消耗 API。

输入（只读）
    生态环境法律法规/、生态环境标准规范/、生态环境监管执法/

输出
    _工作记录/方案设计/域C-Form覆盖率数据.md

运行
    python _脚本代码/数据统计/域C_Form覆盖率.py
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
OUT = WORKSPACE / "_工作记录/方案设计/域C-Form覆盖率数据.md"

# ── 结构抽取器 ────────────────────────────────────────────
CN_NUM = "一二三四五六七八九十百零〇两"
ARTICLE = re.compile(rf"第([{CN_NUM}\d]+)条")
SECTION_NO = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+\S", re.M)      # 标准条款号 3.1 / 4.2.3
ENACT = re.compile(r"自\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日起(?:施行|实施)")
ANY_DATE = re.compile(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")
LAW_CITE = re.compile(r"《([^》]{2,60})》")
ARTICLE_CITE = re.compile(rf"《([^》]{{2,60}})》\s*第([{CN_NUM}\d]+)条")
FINE_RANGE = re.compile(
    rf"(\d+(?:\.\d+)?)\s*(万)?\s*元\s*(?:以上|至|-|—|~)\s*(\d+(?:\.\d+)?)\s*(万)?\s*元")
FINE_ACTUAL = re.compile(r"(?:罚款|处以|处罚款)\s*(?:人民币)?\s*(\d+(?:\.\d+)?)\s*(万)?\s*元")
LIMIT_VALUE = re.compile(
    r"\d+(?:\.\d+)?\s*(?:mg/m3|mg/m³|mg/L|μg/m3|µg/m3|ng\s*TEQ|dB|倍)")
EXCEED = re.compile(r"超标|超过.{0,10}标准|超出.{0,10}限值")
NO_PENALTY = re.compile(r"不予(?:行政)?处罚|免予处罚|不予立案")
LIST_CITE = re.compile(r"〔?不予(?:行政)?处罚事项清单|裁量(?:标准|基准|规则|办法)")
MANDATORY = re.compile(r"强制性|必须严格执行|强制执行")
GUIDANCE = re.compile(r"指导性标准|推荐性|参照执行")
JURISDICTION_HINT = re.compile(
    r"(省|市|自治区|县|区|盟|自治州)(?:人民)?(?:政府|生态环境|环境保护|人大)")
RECTIFY_PLAN = re.compile(r"整改方案|整治方案|整改措施|整改任务|销号")
RECTIFY_TARGET = re.compile(r"(\d{4})\s*年\s*(?:底|年底|12月)?\s*前\s*完成|前完成|按期完成")
RESPONSIBILITY = re.compile(r"失职失责|履职不到位|监管不力|敷衍应对|推进不力|以罚代管|问责")
PROBLEM = re.compile(r"突出问题|问题突出|屡查屡犯|边改边犯|未得到有效解决|群众反映强烈")
SUBJECT = re.compile(r"公司|企业|单位|厂|集团|当事人")
BEHAVIOR = re.compile(r"倾倒|堆放|排放|处置|贮存|运输|焚烧|建设|投产|验收|监测|申报|许可")
OBJECT = re.compile(r"固体废物|危险废物|废水|废气|粉尘|垃圾|污泥|飞灰|渗滤液|噪声|排污许可证")


@dataclass
class Rec:
    path: Path
    text: str
    kind: str                       # law | standard | case | inspect
    feat: dict[str, bool] = field(default_factory=dict)
    arts: list[str] = field(default_factory=list)


def load(kind: str, roots: list[Path], cap: int | None = None) -> list[Rec]:
    files: list[Path] = []
    for r in roots:
        if r.exists():
            files.extend(sorted(r.rglob("*.md")))
    if cap:
        files = files[:cap]
    recs: list[Rec] = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rec = Rec(path=f, text=text, kind=kind)
        rec.feat = {
            "articles": bool(ARTICLE.search(text)),
            "section_no": len(SECTION_NO.findall(text)) >= 3,
            "enact": bool(ENACT.search(text)),
            "any_date": bool(ANY_DATE.search(text)),
            "law_cite": len(set(LAW_CITE.findall(text))) >= 1,
            "multi_cite": len(set(LAW_CITE.findall(text))) >= 2,
            "article_cite": bool(ARTICLE_CITE.search(text)),
            "fine_range": bool(FINE_RANGE.search(text)),
            "fine_actual": bool(FINE_ACTUAL.search(text)),
            "limit_value": bool(LIMIT_VALUE.search(text)),
            "exceed": bool(EXCEED.search(text)),
            "no_penalty": bool(NO_PENALTY.search(text)),
            "list_cite": bool(LIST_CITE.search(text)),
            "mandatory": bool(MANDATORY.search(text)),
            "guidance": bool(GUIDANCE.search(text)),
            "jurisdiction": bool(JURISDICTION_HINT.search(text)),
            "rectify": bool(RECTIFY_PLAN.search(text)),
            "responsibility": bool(RESPONSIBILITY.search(text)),
            "problem": bool(PROBLEM.search(text)),
            "subject": bool(SUBJECT.search(text)),
            "behavior": bool(BEHAVIOR.search(text)),
            "object": bool(OBJECT.search(text)),
        }
        rec.arts = ARTICLE.findall(text)
        recs.append(rec)
    return recs


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:.1f}%" if d else "—"


# ── 候选 Task Form：id、名称、所需证据要素（AND 组合）、归属语料 ──
FORMS: list[dict] = [
    # Family 1 规范检索与适用
    {"id": "RE-C1", "name": "规范定位（行为→候选条款）",
     "corpus": "case", "need": ["behavior", "object", "article_cite"]},
    {"id": "RE-C2", "name": "规范适用性判断（版本/法域）",
     "corpus": "law", "need": ["enact", "articles"]},
    {"id": "RE-C2b", "name": "地方裁量清单适用（法域）",
     "corpus": "case", "need": ["list_cite", "jurisdiction"]},
    # Family 2 要件匹配
    {"id": "RE-C3", "name": "违法构成要件齐备性",
     "corpus": "case", "need": ["subject", "behavior", "object", "article_cite"]},
    {"id": "RE-C4", "name": "法条竞合与择一适用",
     "corpus": "case", "need": ["multi_cite", "article_cite"]},
    # Family 3 裁量与边界
    {"id": "RE-C5", "name": "罚款幅度合规检查",
     "corpus": "case", "need": ["fine_range", "fine_actual"]},
    {"id": "RE-C6", "name": "不予处罚情形认定",
     "corpus": "case", "need": ["no_penalty", "article_cite", "list_cite"]},
    # Family 4 督察整改闭环
    {"id": "RE-C7", "name": "整改进展达标核验",
     "corpus": "inspect", "need": ["rectify", "limit_value", "any_date"]},
    {"id": "RE-C8", "name": "责任主体认定",
     "corpus": "inspect", "need": ["responsibility", "subject"]},
    {"id": "RE-C9", "name": "环境问题定性",
     "corpus": "inspect", "need": ["problem", "behavior", "object"]},
    # Family 5 标准限值
    {"id": "RE-C10", "name": "排放限值符合性判断",
     "corpus": "standard", "need": ["limit_value", "section_no"]},
    {"id": "RE-C10b", "name": "限值符合性（案例侧：超标认定）",
     "corpus": "case", "need": ["limit_value", "exceed", "article_cite"]},
]


def main() -> None:
    print("loading corpora ...", file=sys.stderr)
    corpora = {
        "law": load("law", [
            WORKSPACE / "生态环境法律法规/法律",
            WORKSPACE / "生态环境法律法规/行政法规",
            WORKSPACE / "生态环境法律法规/规章",
        ]),
        "standard": load("standard", [WORKSPACE / "生态环境标准规范"]),
        "case": load("case", [
            WORKSPACE / "生态环境监管执法/类案法条推荐/现有系统案例库"]),
        "inspect": load("inspect", [
            WORKSPACE / "生态环境监管执法/类案法条推荐/督察管理"]),
    }
    sizes = {k: len(v) for k, v in corpora.items()}
    print(f"sizes: {sizes}", file=sys.stderr)

    lines: list[str] = []
    lines.append("# 域 C 候选 Task Form 覆盖率数据")
    lines.append("")
    lines.append(f"> 由 `_脚本代码/数据统计/域C_Form覆盖率.py` 生成，"
                 f"生成时间 {datetime.now():%Y-%m-%d %H:%M}")
    lines.append("> 覆盖率 = 同时满足该 Form 全部证据要素的文档数 ÷ 该类语料总数。"
                 "纯本地结构判定，未调用模型。")
    lines.append("")

    lines.append("## 1. 语料规模")
    lines.append("")
    lines.append("| 语料类别 | 文件数 |")
    lines.append("| --- | --- |")
    for k, v in sizes.items():
        lines.append(f"| {k} | {v} |")
    lines.append("")

    lines.append("## 2. 候选 Form 覆盖率")
    lines.append("")
    lines.append("| Form | 名称 | 语料 | 满足篇数 | 覆盖率 |")
    lines.append("| --- | --- | --- | --- | --- |")
    summary = []
    for form in FORMS:
        recs = corpora[form["corpus"]]
        hit = sum(1 for r in recs if all(r.feat.get(f) for f in form["need"]))
        lines.append(f"| {form['id']} | {form['name']} | {form['corpus']} | "
                     f"{hit} / {len(recs)} | {pct(hit, len(recs))} |")
        summary.append((form["id"], form["name"], form["corpus"], hit, len(recs)))
    lines.append("")

    lines.append("## 3. 单项证据要素可得性（用于回退设计）")
    lines.append("")
    feats = sorted({f for form in FORMS for f in form["need"]})
    lines.append("| 要素 | " + " | ".join(sizes) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in sizes) + " |")
    for f in feats:
        cells = [pct(sum(1 for r in corpora[k] if r.feat.get(f)), sizes[k]) for k in sizes]
        lines.append(f"| `{f}` | " + " | ".join(cells) + " |")
    lines.append("")

    lines.append("## 4. 每类的证据要素全貌")
    lines.append("")
    all_feats = sorted({k for r in corpora["law"] for k in r.feat})
    lines.append("| 要素 | " + " | ".join(sizes) + " |")
    lines.append("| --- | " + " | ".join("---" for _ in sizes) + " |")
    for f in all_feats:
        cells = [pct(sum(1 for r in corpora[k] if r.feat.get(f)), sizes[k]) for k in sizes]
        lines.append(f"| `{f}` | " + " | ".join(cells) + " |")
    lines.append("")

    # 条文数分布（决定 Norm 切分粒度）
    lines.append("## 5. Norm 切分粒度实测")
    lines.append("")
    lines.append("| 语料 | 有「第X条」 | 条文数中位 | 最大 | 有条款号(N.N) | 含施行日期 | 含法域线索 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for k, recs in corpora.items():
        if not recs:
            continue
        counts = sorted(len(r.arts) for r in recs)
        withart = sum(1 for r in recs if r.feat["articles"])
        secno = sum(1 for r in recs if r.feat["section_no"])
        enact = sum(1 for r in recs if r.feat["enact"])
        juris = sum(1 for r in recs if r.feat["jurisdiction"])
        lines.append(f"| {k} | {pct(withart, len(recs))} | {counts[len(counts)//2]} | "
                     f"{counts[-1]} | {pct(secno, len(recs))} | "
                     f"{pct(enact, len(recs))} | {pct(juris, len(recs))} |")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"written: {OUT}")


if __name__ == "__main__":
    main()
