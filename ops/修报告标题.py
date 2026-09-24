#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修语料 front matter 的 title：被截断/通用/空 → 用文件名（项目名）。

背景（2026-09-21 实跑发现）：
  索引里 103,774 个块（占环评报告块 47.3%）标题是「环境影响报告书」「一、建设项目基本情况」
  「进行环境影响评价并公示环境影响报告书。本环境影响报告书第三章部分监测数据、第」这类
  无辨识度字符串 —— 根因在**源头 md 的 front matter 就写着这些**（title 取自 PDF 首行/表格首格），
  而**文件名才是项目名**（例：兰州畜牧现代化生猪养殖及配套项目环评报告书.md）。

判定规则（只改"明显是坏标题"的，好标题一律不动）：
  1. title 缺失 / None / NaN            → 用文件名
  2. title 命中通用词表                  → 用文件名
  3. title 是文件名的前缀（被截断）        → 用文件名
  4. title 长度 ≤ 8 或结尾像被切断        → 用文件名
  5. 其余保持不变

用法：
  python 修报告标题.py --dry-run     # 只打印将要改的（默认）
  python 修报告标题.py --apply       # 真改（先备份到 _backup_标题修正_日期/）
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

BUNDLE_ROOT = Path("/data/fagui_rag/okf_bundles")
BACKUP_DIR = Path("/data/fagui_rag/_backup_标题修正_20260921")
FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

GENERIC = {
    "环境影响报告书", "环境影响报告书 （信息公开版）", "环境影响报告表",
    "建设项目环境影响报告表", "建设项目环境影响报告书",
    "一、建设项目基本情况", "《建设项目环境影响报告表》编制说明",
    "建设项目环境保护设施竣工验收监测报告表",
    "竣工环境保护验收监测报告表", "环境影响评价报告书", "环境影响报告",
    "建设项目环境影响评价文件", "环境影响评价文件",
}
TAIL_CUT = ("年产", "年回收拆解", "年拆解")
SKIP_DIRS = ("环评导则",)          # 这几类标题本来就是文件名，无需处理
# 文件名里的噪声（带这些词的文件名不比原标题好，宁可保留原标题）
JUNK = ("看图王", "pdf", "PDF", "压缩", "全文", "公示版", "公示稿", "送审", "报批",
        "扫描", "副本", "copy", "最终", "W0", "(1)", "（1）", "未命名")
# 文件名去掉原标题后，若以这些词开头 → 原标题其实是「完整的项目名」，只是文件名多了报告类型后缀
CONT = re.compile(r"^(验收|竣工|环境影响|环评|报告|公示|全本|文本|文件|资料|批复|"
                  r"监测|评估|调查|方案|书|表|稿|及|与|的|之|（|\(|-|_)")


def clean_stem(stem: str) -> str:
    """把文件名清洗成「项目名」：去编号/日期/PDF 前缀，去公示版本后缀。"""
    s = stem
    s = re.sub(r"^PDF\s*[（(][^)）]*[)）]\s*[-—]*\s*", "", s, flags=re.I)   # PDF（压缩版）--
    s = re.sub(r"^PDF\s*[-—]+\s*", "", s, flags=re.I)
    s = re.sub(r"^\d{8}\s*[^0-9]{0,8}[-—\s]*", "", s)                      # 20190924公示稿-
    s = re.sub(r"^\d{4}\s*[-—]\s*", "", s)                                 # 2020 - 
    s = re.sub(r"^\d+[.、\-_\s]+", "", s)                                  # 1. / 1、 / 01_
    s = re.sub(r"[（(]\s*(公示版|信息公开版|送审版|报批版|全本|压缩版|1)\s*[)）]", "", s)
    s = re.sub(r"[-—_\s]*(公示版本|公示稿|报批版|送审版|全本公示|pdf版全文|_看图王)$", "", s,
               flags=re.I)
    s = re.sub(r"[-—_\s]*(验收报告文本|报告文本|公示文本|文本|全本)$", "", s)
    s = s.strip(" -_·、.（）()")
    # 去掉尾部不配对的括号片段（例：G309…报告表（生态影响类 → G309…报告表）
    while s and s.count("（") + s.count("(") > s.count("）") + s.count(")"):
        s = s[: max(s.rfind("（"), s.rfind("("))].strip(" -_·、.（）()")
    return s


def norm(s: str) -> str:
    return re.sub(r"[\s　()（）【】\[\]、，,。.．·\-—_]+", "", s)


def assess(new: str, old: str) -> str:
    """候选新标题可用吗？不可用返回原因。"""
    if not new or len(norm(new)) < 6:
        return "候选过短"
    if re.fullmatch(r"W\d{8,}", new):
        return "候选是 PDF 哈希名"
    if re.fullmatch(r"[A-Za-z0-9\s\-_.]+", new):
        return "候选是纯编号/字母"
    hit = [j for j in JUNK if j in new]
    if hit:
        return "候选含噪声 " + "/".join(hit)
    if norm(new) == norm(old):
        return "与原标题相同"
    return ""


def new_title(old, stem: str) -> tuple[str, str]:
    """返回 (新标题, 原因)；('', '需人工（…）') = 原标题坏但候选也坏，保持原样待人工。"""
    cand = clean_stem(stem)
    if not isinstance(old, str) or not old.strip():
        why = assess(cand, "")
        return ("", f"需人工（原标题空；{why}）") if why else (cand, "空/None/NaN")
    t = old.strip()
    nt, ns = norm(t), norm(cand)
    bad_old = ""
    if t in GENERIC:
        bad_old = "通用词"
    elif t.startswith("Col1"):
        bad_old = "表格串"
    elif re.fullmatch(r"[\d\s\-_.A-Za-z]+", t) or len(norm(t)) <= 8:
        bad_old = "过短/纯编号"
    elif ns and nt and ns.startswith(nt) and len(nt) < len(ns):
        rest = ns[len(nt):]
        if CONT.match(rest):
            return "", ""          # 原标题是完整项目名，文件名只是多了「环境影响报告书」后缀
        bad_old = "被截断（是文件名前缀）"
    elif t.endswith(TAIL_CUT):
        bad_old = "结尾被切断"
    if not bad_old:
        return "", ""
    why = assess(cand, t)
    if why:
        return "", f"需人工（{bad_old}；{why}）"
    return cand, bad_old


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="默认行为，显式写上也无妨")
    ap.add_argument("--root", default=str(BUNDLE_ROOT))
    args = ap.parse_args()
    root = Path(args.root)

    changes, manual, reasons, stats = [], [], Counter(), Counter()
    for md in sorted(root.rglob("*.md")):
        rel = md.relative_to(root)
        if rel.parts and rel.parts[0] in SKIP_DIRS:
            continue
        text = md.read_text(encoding="utf-8", errors="replace")
        m = FRONTMATTER.match(text)
        if not m:
            stats["无 front matter"] += 1
            continue
        fm_text = m.group(1)
        # 只处理报告类：标准/法规的标题本来就规整（文件名=标题+标准号，会被误判成"截断"）
        tm_type = re.search(r"^type:[ \t]*(.*)$", fm_text, re.MULTILINE)
        doc_type = (tm_type.group(1).strip() if tm_type else "")
        if doc_type != "report":
            stats["非报告类（跳过）"] += 1
            continue
        tm = re.search(r"^title:[ \t]*(.*)$", fm_text, re.MULTILINE)
        old_raw = tm.group(1).strip() if tm else None
        if old_raw is not None and old_raw in ("", "~", "null", ".nan", "nan", "None"):
            old = ""
        else:
            old = old_raw
        new, why = new_title(old, md.stem)
        stats["扫描文件"] += 1
        if not new:
            if why.startswith("需人工"):
                stats["需人工"] += 1
                reasons[why] += 1
                manual.append((rel, old, md.stem, why))
            else:
                stats["保持原样"] += 1
            continue
        stats["需修改"] += 1
        reasons[why] += 1
        changes.append((md, rel, old, new, why))

    print(f"扫描 {stats['扫描文件']} 份 md（跳过 {list(SKIP_DIRS)}）")
    print(f"  非报告类跳过 {stats['非报告类（跳过）']} 份；报告类里："
          f"需修改 {stats['需修改']}、保持原样 {stats['保持原样']}、"
          f"**需人工 {stats['需人工']}**、无 front matter {stats['无 front matter']}")
    print("修改原因分布：", dict(reasons.most_common()))
    print("\n前 20 条预览（旧 → 新）：")
    for _, rel, old, new, why in changes[:20]:
        print(f"  [{why}] {old[:34] or '（空）'}")
        print(f"        → {new[:70]}")
    if manual:
        print(f"\n需人工的（原标题坏、文件名也坏，保持原样）前 12 条：")
        for rel, old, stem, why in manual[:12]:
            print(f"  {why[:38]}\n      旧：{old[:40] or '（空）'}\n      名：{stem[:60]}")
    print(f"\n（共 {len(changes)} 条待改，完整清单写 /home/test/标题修改清单.tsv）")
    with open("/home/test/标题修改清单.tsv", "w", encoding="utf-8") as f:
        f.write("文件\t原因\t旧标题\t新标题\n")
        for _, rel, old, new, why in changes:
            f.write(f"{rel.as_posix()}\t{why}\t{old}\t{new}\n")

    if not args.apply:
        print("\n【dry-run】未改动任何文件。加 --apply 才真改。")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    for md, rel, old, new, why in changes:
        bak = BACKUP_DIR / rel
        bak.parent.mkdir(parents=True, exist_ok=True)
        if not bak.exists():
            shutil.copy2(md, bak)          # 归档不删除：原件留底
        text = md.read_text(encoding="utf-8", errors="replace")
        new_text, n = re.subn(r"^title:[ \t]*.*$", f"title: {new}", text,
                              count=1, flags=re.MULTILINE)
        if n != 1:
            print(f"  ⚠️ 未替换到 title 行：{rel}")
            continue
        md.write_text(new_text, encoding="utf-8")
        done += 1
    print(f"\n已修改 {done} 份；原件备份在 {BACKUP_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
