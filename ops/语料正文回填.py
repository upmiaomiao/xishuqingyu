#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""语料正文回填：把 md 里"死链图片引用"的位置，用同源 PDF 的原文补回来。

问题
----
OKF bundle 里 2267/3647 份 md 含 `![](images/<hash>.jpg)`，而 images/ 全部缺失
（19060 处引用，0 张图存世）。这些位置原本是**标准限值表、引用文件表、排污许可台账表**，
数值因此在索引里完全不存在 —— 线上回答只能说"材料未提供表1数值"。

做法（锚点式，不依赖表格识别）
----
md 正文是从 PDF 转来的，所以图像槽位前后的文字在 PDF 里都能找到。
对每个图像槽位：
  1. 取槽位**前一段文本的尾部**作前锚点，**后一段文本的头部**作后锚点；
  2. 在 PDF 文本层的归一化串里先后定位两个锚点；
  3. 两锚点之间的 PDF 原文，就是这张图原本承载的内容 —— 回填到槽位处。
这样连 find_tables 检不出的无框线表格（如 GB 18599）也能补回来。

安全约束
----
· 只替换图片引用本身，**不删改任何原有文字**（机械校验：原文是新文的子序列）；
· PDF 里找不到锚点就**保持原样**，不猜、不补；
· 回填内容若已在原文中出现（重复），跳过；
· 输出写到独立的暂存目录，不原地改线上语料。

用法
----
  python3 语料正文回填.py scan  --out /tmp/targets.json
  python3 语料正文回填.py repair --targets /tmp/targets.json --stage /data/fagui_rag/okf_bundles_stage
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter

import fitz

BUNDLE_DEFAULT = "/data/fagui_rag/okf_bundles"
PDF_DEFAULT = "/data/fagui_pdf"

IMG_RE = re.compile(r"!\[\]\(images/[0-9A-Za-z._-]+\.(?:jpg|jpeg|png)\)")
SRC_RE = re.compile(r"^source_path:\s*(.+)$", re.M)
LATEX_RE = re.compile(r"\$[^$]*\$")
MD_NOISE = set("#>*`|_[]()\\")
ANCHOR_LENS = (48, 36, 26, 18, 12)
MIN_FILL = 6
MAX_FILL = 20000
CLUSTER_GAP = 40        # 两个图片引用之间骨架长度小于此值，就当作同一张被拆开的表
KW = re.compile(r"固体废物|生活垃圾|焚烧|填埋|危废|危险废物|污泥|飞灰|渗滤液")

# 骨架匹配：只认汉字/字母/数字，其余（空白、标点、数学符号）一律丢弃。
# 理由：md 与 PDF 的标点、全角半角、连字符经常不一致，逐字符比对会大面积假失败。
FW_TABLE = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ％～－（）",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz%~-()")
KEEP = re.compile(r"[0-9A-Za-z\u4e00-\u9fff\u3400-\u4dbf]")


def halfwidth(text: str) -> str:
    """全角数字/字母/常用符号转半角，保持语义不变。

    PDF 文本层里限值常用全角（'１００'、'６～９'），与用户提问里的半角写法
    字面不一致，会削弱检索命中，也会让"某数值是否在文中"类校验失效。
    """
    return (text or "").translate(FW_TABLE)


# ---------- 文本处理 ----------

def skel_map(raw: str):
    """骨架归一化，并保留 骨架下标→原串下标 的映射（用于最后取原文）。"""
    buf, idx = [], []
    for i, ch in enumerate(raw):
        c = ch.translate(FW_TABLE)
        if KEEP.match(c):
            buf.append(c)
            idx.append(i)
    return "".join(buf), idx


def anchors(text: str, tail: bool):
    """由 md 文本生成候选锚点（骨架化、由长到短）。"""
    s = LATEX_RE.sub(" ", text or "")
    s = "".join(ch.translate(FW_TABLE) for ch in s if KEEP.match(ch.translate(FW_TABLE)))
    out = []
    for L in ANCHOR_LENS:
        if len(s) >= L:
            out.append(s[-L:] if tail else s[:L])
    return out


def clean_fill(text: str) -> str:
    """回填片段清理：全角转半角、压掉多余空行、去掉行尾空格。"""
    lines = [ln.rstrip() for ln in halfwidth(text).splitlines()]
    out, blank = [], 0
    for ln in lines:
        if not ln.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        out.append(ln)
    return "\n".join(out).strip()


# ---------- 段落级差集（补"被无声丢掉、连占位符都没有"的内容） ----------

APPEND_HEAD = "\n\n## 附：原文 PDF 补录（md 转换缺失部分，按原文顺序）\n\n"
TABLE_HEAD = "\n\n## 附：原文 PDF 表格（结构化还原，按页顺序）\n\n"


def _cell(v) -> str:
    if v is None:
        return ""
    t = halfwidth(str(v))
    t = re.sub(r"\s*\n\s*", "", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t.replace("|", "\\|")


def rows_to_md(rows) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    fixed = [[_cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(fixed[0]) + " |",
           "|" + "|".join([" --- "] * width) + "|"]
    for r in fixed[1:]:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def pdf_tables(pdf_path: str):
    """用 PyMuPDF 把 PDF 里有框线的表格还原成 markdown（保留行列对齐）。

    原始文本层顺序会把跨列单元格打乱（例如 '≥95' 被挤到下一段），
    结构化还原能拿到行列关系正确的表，是限值类内容最可靠的来源。
    """
    doc = fitz.open(pdf_path)
    out = []
    for pno in range(doc.page_count):
        try:
            tabs = doc[pno].find_tables()
        except Exception:
            continue
        if not tabs or not tabs.tables:
            continue
        for tb in tabs.tables:
            try:
                md = rows_to_md(tb.extract())
            except Exception:
                continue
            if md and md.count("\n") >= 1:
                out.append((pno + 1, md))
    doc.close()
    return out


def pdf_paragraphs(raw: str):
    """把 PDF 文本切成段落：连续非空行并成一段。"""
    paras, cur = [], []
    for ln in raw.splitlines():
        s = ln.strip()
        if s:
            cur.append(s)
        elif cur:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return paras


def md_shingles(md_text: str, k: int = 20):
    """把 md 骨架切成 k 字滑窗集合，用于判断"某段内容是否已在文中"。"""
    sk = skel_map(md_text)[0]
    return {sk[i:i + k] for i in range(max(0, len(sk) - k + 1))}, sk


def is_covered(sk: str, shingles, k: int = 20, cover: float = 0.35) -> bool:
    """段落骨架的滑窗有多大比例能在 shingles 里找到；达到 cover 即认为"已存在"。"""
    if len(sk) < k:
        return True
    windows = len(sk) - k + 1
    hit = 0
    for i in range(windows):
        if sk[i:i + k] in shingles:
            hit += 1
            if hit / windows >= cover:
                return True
    return False


def missing_paragraphs(raw: str, shingles, k: int = 20, cover: float = 0.35):
    """挑出 PDF 里有、md 里没有的段落。

    · 判据用 shingle 覆盖率：只测段落前缀会因为分页断句而大面积误判重复，必须整段测；
    · PDF 里重复出现 >3 次的段落（页眉页脚/编号装饰）不补。
    """
    paras = pdf_paragraphs(raw)
    skels = [skel_map(p)[0] for p in paras]
    freq = Counter(s for s in skels if s)
    out, seen = [], set()
    for para, sk in zip(paras, skels):
        if len(sk) < 12 or freq[sk] > 3:
            continue
        key = sk[:40]
        if key in seen or is_covered(sk, shingles, k, cover):
            continue
        seen.add(key)
        out.append(para)
    return out


# ---------- PDF ----------

def load_pdf_text(pdf_path: str):
    doc = fitz.open(pdf_path)
    raw = "\n".join(doc[i].get_text() for i in range(doc.page_count))
    pages = doc.page_count
    doc.close()
    sk, idx = skel_map(raw)
    return raw, sk, idx, pages


# ---------- 选择 ----------

def iter_bundles(root):
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            if f.endswith(".md"):
                yield os.path.join(dp, f)


def locate_pdf(md_path, bundle_root, pdf_root):
    """由 bundle md 的 source_path 定位 PDF；失败则退回同名同目录。"""
    try:
        t = open(md_path, encoding="utf-8", errors="replace").read(4000)
    except Exception:
        return None
    m = SRC_RE.search(t)
    if m:
        src = m.group(1).strip().strip("'\"")
        cand = os.path.join(pdf_root, os.path.splitext(src)[0] + ".pdf")
        if os.path.isfile(cand):
            return cand
    rel = os.path.relpath(md_path, bundle_root)
    cand = os.path.join(pdf_root, os.path.splitext(rel)[0] + ".pdf")
    return cand if os.path.isfile(cand) else None


def cmd_scan(a):
    targets, no_pdf, no_pdftext = [], 0, 0
    for md in iter_bundles(a.bundle):
        text = open(md, encoding="utf-8", errors="replace").read()
        refs = IMG_RE.findall(text)
        if not refs:
            continue
        rel = os.path.relpath(md, a.bundle)
        pdf = locate_pdf(md, a.bundle, a.pdf)
        if not pdf:
            no_pdf += 1
            continue
        try:
            raw, _nm, _idx, pages = load_pdf_text(pdf)
        except Exception:
            no_pdftext += 1
            continue
        if len(raw) < 200:
            no_pdftext += 1
        targets.append({
            "rel": rel,
            "md_chars": len(text),
            "pdf_chars": len(raw),
            "gap": len(raw) - len(text),
            "refs": len(refs),
            "pages": pages,
            "pdf": pdf,
            "keyword": bool(KW.search(os.path.basename(rel))) or bool(KW.search(text[:3000])),
        })
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(targets, f, ensure_ascii=False, indent=1)
    gaps = [t["gap"] for t in targets]
    print(f"含图片引用的文档 {len(targets)}（无 PDF {no_pdf}，PDF 无文本层 {no_pdftext}）")
    print(f"正文字数缺口合计 {sum(g for g in gaps if g > 0):,}"
          f"   缺口>1500 字 {sum(1 for g in gaps if g > 1500)} 份"
          f"   固废/焚烧相关 {sum(1 for t in targets if t['keyword'])} 份")
    print(f"清单 → {a.out}")


# ---------- 回填 ----------

def repair_one(md_path, pdf_path, stage_path, free_search=False, append_missing=True):
    """返回 (状态, 明细)。状态 ∈ ok/skip。"""
    text = open(md_path, encoding="utf-8", errors="replace").read()
    refs = list(IMG_RE.finditer(text))
    if not refs:
        return "skip", {"reason": "无引用"}

    raw, sk, idx, pages = load_pdf_text(pdf_path)
    if len(sk) < 100:
        return "skip", {"reason": "PDF 无文本层"}
    md_sk, _ = skel_map(text)

    out, cursor_md, cursor_pdf = [], 0, 0
    filled = 0
    added = 0
    fallback_used = 0
    absorbed = []          # 被补入内容吸收掉的簇内小字串（校验时要排除）
    why = Counter()
    # 把间距很近的图片引用聚成一个"簇"：MinerU 常把一张大表拆成多张图，
    # 图与图之间只夹着页眉之类的短字串。整簇用一段 PDF 原文覆盖；
    # 被覆盖掉的小字串随后校验是否已包含在补入内容里，未包含则原样补回。
    clusters = []
    for m in refs:
        if clusters:
            prev = clusters[-1]
            between = text[prev[1]:m.start()]
            if len(skel_map(between)[0]) < CLUSTER_GAP:
                prev[1] = m.end()
                prev[2].append(between)
                continue
        clusters.append([m.start(), m.end(), []])

    for start, end, betweens in clusters:
        # 锚点文本里必须剔除图片引用本身，否则 'images…jpg' 骨架会污染锚点
        before = IMG_RE.sub("", text[:start])
        after = IMG_RE.sub("", text[end:])
        out.append(text[cursor_md:start])
        fill = ""
        pos_a = pos_b = -1
        for an in anchors(before, tail=True):
            p = sk.find(an, cursor_pdf)
            if p >= 0:
                pos_a = p + len(an)
                break
        if pos_a < 0 and free_search:
            # 诊断/兜底：不要求命中位置在游标之后。
            # MinerU 会重排内容（把表格挪到引用文字之后），此时单调游标会卡住。
            for an in anchors(before, tail=True):
                p = sk.find(an)
                if p >= 0:
                    pos_a = p + len(an)
                    fallback_used += 1
                    break
        if pos_a >= 0:
            for an in anchors(after, tail=False):
                p = sk.find(an, pos_a)
                if p >= 0:
                    pos_b = p
                    break
        if pos_a >= 0 and pos_b > pos_a:
            seg = raw[idx[pos_a]: idx[pos_b - 1] + 1] if pos_b - 1 < len(idx) else ""
            fill = clean_fill(seg)
        # 后锚点找不到时不做退化猜测（宁可留空，也不补可能错位的内容）

        if pos_a < 0:
            why["前锚点在 PDF 中找不到"] += 1
        elif pos_b <= pos_a:
            why["后锚点在 PDF 中找不到"] += 1
        elif len(fill) < MIN_FILL:
            why["该处 PDF 无有效内容"] += 1
        elif len(fill) > MAX_FILL:
            why["内容过长（疑似错位）"] += 1
        elif skel_map(fill)[0][:30] in md_sk:
            why["内容已在原文中"] += 1
        else:
            why["已回填"] += 1
            filled += 1
            added += len(fill)
            out.append("\n" + fill + "\n")
            # 簇内被覆盖掉的小字串（页眉等）若不在补入内容里，原样补回，保证不丢字
            fill_sk = skel_map(fill)[0]
            for b in betweens:
                bs = skel_map(b)[0]
                if bs and bs not in fill_sk:
                    out.append(b)
                    added += len(b)
                elif bs:
                    absorbed.append(b)
            cursor_md = end
            if pos_b > 0:
                cursor_pdf = pos_b
            continue

        out.append(text[start:end])
        cursor_md = end
        if pos_b > 0:
            cursor_pdf = pos_b

    out.append(text[cursor_md:])
    new_text = "".join(out)

    # 第二段：段落级差集 —— 补回"被无声丢掉、连占位符都没有"的内容。
    # 只追加到文末，不改动任何既有位置，因此没有错位风险；
    # 已在上面内联补过的段落会被包含测试识别为"已存在"，不会重复。
    appended = 0
    if append_missing:
        shingles, _ = md_shingles(new_text)
        miss = missing_paragraphs(raw, shingles)
        if miss:
            new_text += APPEND_HEAD + "\n\n".join(halfwidth(p) for p in miss) + "\n"
            appended = len(miss)
            shingles, _ = md_shingles(new_text)   # 追加后更新，供表格判重使用

    # 第三段：结构化表格还原 —— 文本层顺序会把表格列打乱，这里按行列还原。
    # 判据：只要 md 里还没有**一模一样的 markdown 表**就补入。
    # 曾经的三种"更聪明"的判据都试过并放弃：
    #   ① shingle 覆盖率判"已存在"→ 小表滑窗太少，被内联乱序文本误判（漏掉 ≥95）；
    #   ② 骨架数字判据 → '≤25 ≥95' 被粘成 '2595'，失效；
    #   ③ 半角化后按独立数字边界判"数值都在文中"→ 判据正确但方向错了：
    #      储油库的 ≤25/≥95 确实以"逐行散文本"形式在文中，可是那种形态分块后会被
    #      并进大段散文，问"排放限值是多少"根本检索不到。表格块（几乎全是
    #      "污染物项目 + 数值"）才是限值类问题最匹配的形态，所以应当照补。
    # 同一份文档里出现多次的相同表格只补一次（seen_tab）。
    tables_added = 0
    if append_missing:
        md_hx = halfwidth(new_text)
        blocks, seen_tab = [], set()
        for pno, md in pdf_tables(pdf_path):
            sk = skel_map(md)[0]
            if len(sk) < 8 or sk in seen_tab:
                continue
            if md.strip() and md.strip() in md_hx:
                continue          # 已经有完全相同的表
            seen_tab.add(sk)
            blocks.append(f"<!-- 第 {pno} 页 -->\n\n{md}")
        if blocks:
            new_text += TABLE_HEAD + "\n\n".join(blocks) + "\n"
            tables_added = len(blocks)

    # 机械校验：骨架级子序列 —— 原文（去掉图片占位符、去掉被吸收的簇内小字串）
    # 必须仍是新文的子序列。骨架级 = 忽略标点空白差异，只认汉字/字母/数字，
    # 因此这条断言真正管的是"内容字符一个不少、顺序不乱"。
    keep = IMG_RE.sub("", text)
    for frag in absorbed:
        keep = keep.replace(frag, "", 1)
    keep_sk = skel_map(keep)[0]
    it = iter(skel_map(new_text)[0])
    if not all(ch in it for ch in keep_sk):
        return "skip", {"reason": "校验失败：原文内容字符不是新文子序列"}

    os.makedirs(os.path.dirname(stage_path), exist_ok=True)
    with open(stage_path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return "ok", {
        "refs": len(refs), "slots": len(clusters), "filled": filled,
        "skipped": len(clusters) - filled,
        "added": added, "appended": appended, "tables": tables_added,
        "md_before": len(text), "md_after": len(new_text),
        "why": dict(why), "fallback": fallback_used,
    }


def cmd_repair(a):
    targets = json.load(open(a.targets, encoding="utf-8"))
    if a.only_keyword:
        targets = [t for t in targets if t["keyword"]]
    if a.min_gap:
        targets = [t for t in targets if t["gap"] >= a.min_gap]
    if a.match:
        targets = [t for t in targets if a.match in t["rel"]]
    targets.sort(key=lambda t: -t["gap"])   # 缺口大的先做，--limit 才有意义
    if a.limit:
        targets = targets[: a.limit]
    print(f"待处理 {len(targets)} 份")

    report, agg = [], Counter()
    for i, t in enumerate(targets, 1):
        md = os.path.join(a.bundle, t["rel"])
        stage = os.path.join(a.stage, t["rel"]) if a.stage else None
        try:
            status, info = repair_one(md, t["pdf"], stage, free_search=a.free_search,
                                      append_missing=not a.no_append)
        except Exception as e:
            status, info = "skip", {"reason": f"{e.__class__.__name__}: {e}"}
        info.update({"rel": t["rel"], "status": status, "gap": t["gap"]})
        report.append(info)
        agg[status] += 1
        if status == "ok":
            agg["filled"] += info.get("filled", 0)
            agg["skipped_slots"] += info.get("skipped", 0)
            agg["added"] += info.get("added", 0)
            agg["appended"] += info.get("appended", 0)
            agg["tables"] += info.get("tables", 0)
            agg["fallback"] += info.get("fallback", 0)
            for k, v in (info.get("why") or {}).items():
                agg["why_" + k] += v
        if i % 25 == 0:
            print(f"  …{i}/{len(targets)}  已回填 {agg['filled']} 处 / 新增 {agg['added']:,} 字")

    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=1)
    print(f"\n处理 {len(targets)} 份：成功 {agg['ok']}  跳过 {agg['skip']}")
    print(f"  回填槽位 {agg['filled']} 处，未能回填 {agg['skipped_slots']} 处")
    for k in sorted(k for k in agg if k.startswith("why_")):
        print(f"    {k[4:]:24s} {agg[k]}")
    print(f"  其中靠回退定位成功 {agg['fallback']} 处")
    print(f"  段落级差集追加 {agg['appended']} 段，结构化表格还原 {agg['tables']} 张")
    print(f"  新增正文 {agg['added']:,} 字")
    if a.report:
        print(f"  明细 → {a.report}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["scan", "repair"])
    ap.add_argument("--bundle", default=BUNDLE_DEFAULT)
    ap.add_argument("--pdf", default=PDF_DEFAULT)
    ap.add_argument("--out", default="/tmp/回填清单.json")
    ap.add_argument("--targets", default=None)
    ap.add_argument("--stage", default=None)
    ap.add_argument("--report", default=None)
    ap.add_argument("--only-keyword", action="store_true")
    ap.add_argument("--min-gap", type=int, default=0)
    ap.add_argument("--match", default=None, help="只处理 relpath 含此子串的文档")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-append", action="store_true",
                    help="不做段落级差集补录（只做占位符内联回填）")
    ap.add_argument("--free-search", action="store_true",
                    help="锚点找不到时允许回退到全文搜索（应对 PDF 与 md 顺序不一致）")
    a = ap.parse_args()
    (cmd_scan if a.cmd == "scan" else cmd_repair)(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
