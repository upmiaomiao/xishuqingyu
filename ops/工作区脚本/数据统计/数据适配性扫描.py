"""数据适配性扫描：把工作区现有原始语料喂给 COT 系统的 raw gate，统计通过率。

用途
    在不消耗任何 LLM API 的前提下，量化「现有原始数据」与「cot-data-construction-code
    的 ingestion 入口契约」之间的差距。
    直接复用生产代码的 ingestion.eligibility.assess_raw_material，保证结论与生产一致。

输入（只读，不修改任何原始数据）
    extracted/垃圾焚烧md-文献 专利 标准/md/incpapers/{cn,en}   → research 域候选
    extracted/垃圾焚烧md-文献 专利 标准/md/patents/{cn,en}     → research 域候选（预期不合格）
    extracted/垃圾焚烧md-文献 专利 标准/md/standard            → 标准文本（预期不合格）
    extracted/环评md/md                                       → process 域候选
    生态环境监管执法/类案法条推荐/现有系统案例库               → regulatory 域候选
    生态环境监管执法/类案法条推荐/督察管理                     → regulatory 域候选
    生态环境法律法规/{法律,行政法规,规章}                      → 法条库可行性（按「第X条」切分率）

输出
    仅打印到 stdout，不落盘。每类抽样上限由 --sample 控制。

运行方式
    python _脚本代码/数据统计/数据适配性扫描.py --sample 150
"""
from __future__ import annotations

import argparse
import random
import re
import sys
from collections import Counter
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
REPO = WORKSPACE / "cot-data-construction-code"
sys.path.insert(0, str(REPO))

from ingestion.eligibility import assess_raw_material  # noqa: E402

ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百零〇\d]+条")
# 法条库 loader 需要的生效日期线索（与 law_repository._parse_effective 同源正则）
EFFECTIVE_RE = re.compile(r"自(\d{4})年(\d{1,2})月(\d{1,2})日起施行")
VERSION_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")

CORPORA = [
    ("research", "垃圾焚烧-论文(中)", WORKSPACE / "extracted/垃圾焚烧md-文献 专利 标准/md/incpapers/cn"),
    ("research", "垃圾焚烧-论文(英)", WORKSPACE / "extracted/垃圾焚烧md-文献 专利 标准/md/incpapers/en"),
    ("research", "垃圾焚烧-专利(中)", WORKSPACE / "extracted/垃圾焚烧md-文献 专利 标准/md/patents/cn"),
    ("research", "垃圾焚烧-标准",     WORKSPACE / "extracted/垃圾焚烧md-文献 专利 标准/md/standard"),
    ("process",  "环评报告",         WORKSPACE / "extracted/环评md/md"),
    ("regulatory", "类案学习要点",   WORKSPACE / "生态环境监管执法/类案法条推荐/现有系统案例库"),
    ("regulatory", "督察通报",       WORKSPACE / "生态环境监管执法/类案法条推荐/督察管理"),
]


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def scan_corpus(domain: str, label: str, root: Path, sample: int, seed: int) -> None:
    if not root.exists():
        print(f"  [缺失] {label}: {root}")
        return
    files = sorted(root.rglob("*.md"))
    if not files:
        print(f"  [空]   {label}")
        return
    rng = random.Random(seed)
    picked = files if len(files) <= sample else rng.sample(files, sample)
    passed = 0
    reasons: Counter[str] = Counter()
    for f in picked:
        result = assess_raw_material(domain, read_text(f))
        if result.eligible:
            passed += 1
        else:
            for r in result.reasons:
                reasons[r] += 1
    rate = 100.0 * passed / len(picked)
    print(f"  {label:<16} 全库 {len(files):>5} 篇 | 抽样 {len(picked):>4} | "
          f"通过 {passed:>4} = {rate:5.1f}%")
    for reason, n in reasons.most_common(3):
        print(f"        未通过主因: {reason} ({n})")


def scan_law_split(sample: int, seed: int) -> None:
    """检查法条 md 能否按「第X条」切分，以及是否带生效日期线索。"""
    print("\n── 法条文本可切分性（LawRepository 需要的结构）──")
    base = WORKSPACE / "生态环境法律法规"
    if not base.exists():
        print(f"  [缺失] {base}")
        return
    files = sorted(base.rglob("*.md"))
    rng = random.Random(seed)
    picked = files if len(files) <= sample else rng.sample(files, sample)
    split_ok = 0
    has_effective = 0
    has_version_date = 0
    counts = []
    for f in picked:
        text = read_text(f)
        n = len(ARTICLE_RE.findall(text))
        counts.append(n)
        if n >= 2:
            split_ok += 1
        if EFFECTIVE_RE.search(text):
            has_effective += 1
        if VERSION_DATE_RE.search(text):
            has_version_date += 1
    total = len(picked)
    if not total:
        return
    counts.sort()
    print(f"  抽样 {total} 部法规")
    print(f"  可按「第X条」切分(>=2条) : {split_ok}/{total} = {100.0*split_ok/total:.1f}%")
    print(f"  含「自..起施行」        : {has_effective}/{total} = {100.0*has_effective/total:.1f}%")
    print(f"  含任意中文日期(沿革兜底): {has_version_date}/{total} = {100.0*has_version_date/total:.1f}%")
    print(f"  条文数 中位数/最大       : {counts[len(counts)//2]} / {counts[-1]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=150, help="每类抽样文件数上限")
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--law-sample", type=int, default=120)
    args = ap.parse_args()

    print(f"raw gate 适配性扫描  抽样上限={args.sample}  seed={args.seed}")
    print("判据 = 生产代码 ingestion.eligibility.assess_raw_material\n")
    current = None
    for domain, label, root in CORPORA:
        if domain != current:
            print(f"════ {domain} 域 ════")
            current = domain
        scan_corpus(domain, label, root, args.sample, args.seed)
    scan_law_split(args.law_sample, args.seed)


if __name__ == "__main__":
    main()
