#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改「材料状态」：把已被废止的法规/标准在 bundle 的 front matter 里标成 已废止。

为什么必须改这里：检索器 `/data/fagui_rag/retriever.py:355` 按索引元数据的 `status`
扣 0.35 分（`ABOLISHED_STATUS` 认「已废止」），**机制现成、一行都不用改**；
真正错的是索引里这些材料的 status 还写着「现行」，于是已废止的法律跟法典平起平坐。

判定依据（逐条可核）：
  · 10 部法律 → 《中华人民共和国生态环境法典》第一千二百四十二条**明列**同时废止，
    法典自 2026-08-15 起施行（该条原文就在语料里，法典自身 379 块 status=现行）。
  · GB 3095—2012 → 被 GB 3095—2026 代替，2026-03-01 起实施（分两阶段：2026-03-01～2030-12-31
    执行过渡阶段限值，2031-01-01 起执行修订后限值）。**库里的目录名自己就写着
    「（2026年3月1日起废止）」**，只有 front matter 的 status 没跟上。

用法：
  python 改材料状态.py                 # 只报告：改哪些文件、现状→目标、涉及索引多少块
  python 改材料状态.py --apply         # 真改（逐份备份到 归档目录，可回滚）
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import sys
import time
from pathlib import Path

BUNDLE = Path("/data/fagui_rag/okf_bundles")
INDEX = Path("/data/fagui_rag/index/chunks.jsonl")
BAK = Path("/home/test/_重构归档_20260922/第二批_前")
FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)

# 法典第1242条的同时废止清单（原文见语料：法律_43/中华人民共和国生态环境法典 第 5356 行）
ABOLISHED_LAWS = [
    "中华人民共和国环境保护法",
    "中华人民共和国环境影响评价法",
    "中华人民共和国海洋环境保护法",
    "中华人民共和国大气污染防治法",
    "中华人民共和国水污染防治法",
    "中华人民共和国土壤污染防治法",
    "中华人民共和国固体废物污染环境防治法",
    "中华人民共和国噪声污染防治法",
    "中华人民共和国放射性污染防治法",
    "中华人民共和国清洁生产促进法",
]
LAW_NOTE = ("已自2026年8月15日起被《中华人民共和国生态环境法典》废止"
            "（法典第一千二百四十二条明列同时废止）；现行依据请查《生态环境法典》")

# 标准：被替代即废止
STD_TARGETS = [
    {
        "must": ["GB 3095—2012"],
        "must_not": ["GB 3095—2026"],          # 2026 版自己的路径里也含"2012"，必须排除
        "status": "已废止",
        "note": "已被《环境空气质量标准》（GB 3095—2026）代替，自2026年3月1日起废止",
    },
]

# 误报排除：这些材料**本身是现行有效的**，只是名字里带"废止"（它们是废止别人的决定）
EXCLUDE = ["关于废止和修改部分省政府规章的决定"]


def yaml_status_line(text: str):
    """返回 (front matter 文本, status 行的起止偏移, 原 status 值)"""
    m = FM.match(text)
    if not m:
        return None, None, None
    fm = m.group(1)
    sm = re.search(r"^status:[ \t]*(.*)$", fm, re.M)
    if not sm:
        return fm, None, None

    def off(x):
        return m.start(1) + x

    return fm, (off(sm.start()), off(sm.end()), sm.group(1).strip()), sm.group(1).strip()


def targets():
    """挑出要改的 md：法律按路径 + front matter type，标准按路径特征。"""
    out = []
    for p in sorted(BUNDLE.rglob("*.md")):
        rel = p.relative_to(BUNDLE).as_posix()
        if "/_归档" in rel or "_只读拉取" in rel:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, span, cur = yaml_status_line(text)
        if fm is None:
            continue
        # 法律：路径里含法名，且 front matter/路径表明它就是这部法律的本体
        for law in ABOLISHED_LAWS:
            if law in rel:
                t = re.search(r"^title:[ \t]*(.*)$", fm, re.M)
                title = t.group(1).strip().strip('"\'') if t else ""
                ty = re.search(r"^type:[ \t]*(.*)$", fm, re.M)
                typ = ty.group(1).strip() if ty else ""
                # 必须是"这部法律本身"：标题等于法名，或标题里含法名且 type 是法律
                if title == law or (law in title and ("法律" in typ or "/法律" in rel)):
                    out.append({"path": p, "rel": rel, "law": law, "cur": cur,
                                "new": "已废止", "note": LAW_NOTE})
                break
        else:
            for spec in STD_TARGETS:
                if all(s in rel for s in spec["must"]) and \
                   not any(s in rel for s in spec["must_not"]):
                    out.append({"path": p, "rel": rel, "law": rel.split("/")[-1][:40],
                                "cur": cur, "new": spec["status"], "note": spec["note"]})
                    break
    return out


def scan_all():
    """通用探测：目录/文件名里明写「废止」，而 front matter 还写着「现行」的 md。

    这一类是**系统性**的：入库时把"废止"信息写进了目录名，却没写进 status，
    而检索器只认 status —— 所以凡是命中这里的，都是同一类漏网。
    命中后从路径里把括注（如「（2026年3月1日起废止）」）抠出来当说明。

    ⚠️ 必须排除的**误报**：文件名叫《…关于废止和修改部分省政府规章的决定》，
    它自己是"废止别人的决定"，本身是现行有效的 —— 路径含"废止"但它不是被废止对象。
    """
    hits = []
    for p in sorted(BUNDLE.rglob("*.md")):
        rel = p.relative_to(BUNDLE).as_posix()
        if "/_归档" in rel or "_只读拉取" in rel:
            continue
        if any(x in rel for x in EXCLUDE):
            continue
        if "废止" not in rel and "失效" not in rel:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        _, _, cur = yaml_status_line(text)
        if cur and cur not in ("已废止", "废止", "已失效", "已作废"):
            tag = ""
            m = re.search(r"[（(]([^（()）]*?(?:废止|失效)[^（()）]*?)[）)]", rel)
            if m:
                tag = m.group(1)
            note = (f"语料目录标注「{tag}」" if tag else "语料目录标注为已废止材料") + \
                   "；引用时请核对现行版本（本条由 2026-09-22 状态体检脚本按目录标注统一修正）"
            hits.append({"path": p, "rel": rel, "law": rel.split("/")[-1][:40],
                         "cur": cur, "new": "已废止", "note": note})
    return hits


def index_counts():
    """每条 source 在线上索引里有多少块、当前 status 是什么 —— 用来预告影响面。"""
    cnt = {}
    if not INDEX.is_file():
        return cnt
    with io.open(INDEX, encoding="utf-8", errors="replace") as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            src = o.get("source") or ""
            if not src:
                continue
            d = cnt.setdefault(src, {})
            st = o.get("status") or "(空)"
            d[st] = d.get(st, 0) + 1
    return cnt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真的写文件（默认只报告）")
    args = ap.parse_args()

    rows = targets()
    cnt = index_counts()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    print("=" * 100)
    print("【要改的材料】（依据：法典第1242条 / GB 3095—2026 代替 GB 3095—2012）")
    print("=" * 100)
    n_idx = 0
    for r in rows:
        ic = cnt.get(r["rel"], {})
        n = sum(ic.values())
        n_idx += n
        flag = "→".join([str(r["cur"]), r["new"]])
        print(f"  [{flag:>14}]  索引 {n:>4} 块 {ic if ic else ''}")
        print(f"                  {r['rel']}")
    print(f"\n  合计 {len(rows)} 份文件，涉及索引 {n_idx} 块")
    if not rows:
        print("  ⚠️ 一个都没匹配到，先别 --apply，检查匹配规则")
        return 1

    # 顺带：把"目录名写着废止、status 还写现行"的材料全扫出来（同类漏网一网打尽）
    print("\n" + "=" * 100)
    print("【通用探测：目录名写「废止」而 status 仍为现行的材料（同一类漏网）】")
    print("=" * 100)
    others = scan_all()
    seen = {r["path"] for r in rows}
    extra = [h for h in others if h["path"] not in seen]
    if not others:
        print("  （没有别的漏网）")
    for h in others:
        ic = cnt.get(h["rel"], {})
        print(f"  status={h['cur']}  索引 {sum(ic.values()):>4} 块   {h['rel'][:96]}")
    print(f"  共 {len(others)} 份，其中 {len(extra)} 份是本次新发现的同类漏网（会一起改）")

    todo = rows + extra

    # 顺带把 GB 3095—2026（现行版）的 front matter 与限值行打出来，供写"过渡期限值"文案用
    print("\n" + "=" * 100)
    print("【GB 3095—2026 现行版：front matter 与限值行（写文案用）】")
    print("=" * 100)
    for p in sorted(BUNDLE.rglob("*.md")):
        rel = p.relative_to(BUNDLE).as_posix()
        if "GB 3095—2026" not in rel or "_附件" not in rel:
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        m = FM.match(text)
        print(f"---------- {rel}")
        if m:
            for ln in m.group(1).splitlines():
                if ln.strip():
                    print("   | " + ln[:150])
        body = text[m.end():] if m else text
        for ln in body.splitlines():
            if re.search(r"PM10|PM2\.5|颗粒物", ln) and re.search(r"\d", ln):
                print("   > " + ln.strip()[:190])

    if not args.apply:
        print("\n【报告模式】未写任何文件。要落地请加 --apply")
        return 0

    BAK.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 100)
    print(f"【落地】备份目录 {BAK}")
    print("=" * 100)
    changed = 0
    manifest = []
    for r in todo:
        text = r["path"].read_text(encoding="utf-8")
        fm, span, cur = yaml_status_line(text)
        if span is None:
            # 没有 status 行 → 在 front matter 末尾补一行
            m = FM.match(text)
            ins = m.start(1) + len(m.group(1))
            new_text = text[:ins] + f"\nstatus: {r['new']}" + text[ins:]
        else:
            i, j, _ = span
            new_text = text[:i] + f"status: {r['new']}" + text[j:]
        # 说明写进独立键：它**不参与嵌入配方**（配方只用 title/description），只给人看
        if "status_note:" not in new_text:
            m = FM.match(new_text)
            ins = m.start(1) + len(m.group(1))
            new_text = new_text[:ins] + f"\nstatus_note: {r['note']}" + new_text[ins:]
        if new_text == text:
            print(f"  = 无需改动 {r['rel'][:90]}")
            continue
        # 备份：**按原目录结构镜像**（早先把整条路径用 __ 拍平成文件名，
        # 结果一份 200 多字符的材料路径直接撞上 255 字节的文件名上限、
        # 备份抛 OSError 把整个脚本打断 —— 于是"一行没改"，比改错更难查）
        dst = BAK / r["rel"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(r["path"], dst)
        r["path"].write_text(new_text, encoding="utf-8")
        changed += 1
        manifest.append({"rel": r["rel"], "old": cur or "", "new": r["new"], "note": r["note"]})
        print(f"  ✅ {cur or '(无)'} → {r['new']}   {r['rel'][:88]}")
    (BAK / f"_清单_{stamp}.json").write_text(
        json.dumps({"at": stamp, "changed": changed, "items": manifest},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  改了 {changed} 份，备份在 {BAK}（回滚=按原路径拷回）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
