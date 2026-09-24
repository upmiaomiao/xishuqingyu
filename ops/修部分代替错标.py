#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正「部分代替被读成整体废止」这一类错标（2026-09-22 第三批，B5 的根因之一）。

怎么发现的：B5（"GB8978 总汞 0.05 是车间口还是三级标准？"）答不出来，一路查到
索引里 GB 8978-1996 有**两份**：一份 2 块标「现行」（只有封面）、一份 30 块标「已废止」——
而"第一类污染物…一律在车间或车间处理设施排放口采样"这句原文**只在后者**。
检索器对「已废止」扣 0.35 分，于是**唯一带答案的那份被自己人压下去了**。

官方登记（全国标准信息公共服务平台，本次联网核实）：
  · 国家标准《污水综合排放标准》 强制性 **现行**
  · 当前标准 **GB 8978-1996 现行**；1996-10-04 发布、1998-01-01 实施；上次复审 2016-12-31 结论"修订"
  · "即将被以下标准替代：GB 20425-2006（**部分代替**）皂素工业水污染物排放标准"
  URL：https://std.samr.gov.cn/gb/search/gbDetailed?id=71F772D7B643D3A7E05397BE0A0AB82A
⇒ 库里那份标「已废止」是**错的**，而且错法与 A2 里查到的 HJ 915 一模一样：
  **"部分代替"被当成了"整体废止"**。

本脚本做两件事：
  ① 把 GB 8978-1996 那份错标的 status 改回「现行」并写明依据（可回滚）；
  ② 扫出**同类嫌疑**：凡 status=已废止、而它自己路径/正文里出现「部分代替」的材料，
     一律只**报告**不自动改（要不要改得逐条查官方登记）。

用法：
  python 修部分代替错标.py            # 只报告
  python 修部分代替错标.py --apply    # 真改 ①（逐份备份到归档目录）
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
BAK = Path("/home/test/_重构归档_20260922/第三批_前")
FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
STAMP = time.strftime("%Y%m%d_%H%M%S")

FIX = {
    "must": ["8978"],
    "must_not": ["20425", "20426"],          # 那两个是"部分代替别人"的标准，不是被改对象
    "new": "现行",
    "note": ("现行有效：全国标准信息公共服务平台登记为「强制性 现行」，1996-10-04 发布、"
             "1998-01-01 实施；仅被 GB 20425-2006（皂素工业）、GB 20426-2006（煤炭工业）"
             "**部分代替**，整体并未废止（2026-09-22 联网核实）"),
}
SUSPECT = re.compile(r"部分代替|部分废止")


def fm_of(text: str):
    m = FM.match(text)
    return m.group(1) if m else None


def status_of(fm: str):
    m = re.search(r"^status:[ \t]*(.*)$", fm, re.M)
    return m.group(1).strip() if m else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    print("扫描 %s" % BUNDLE)
    fix_hits, suspects = [], []
    for p in sorted(BUNDLE.rglob("*.md")):
        rel = p.relative_to(BUNDLE).as_posix()
        if "/_归档" in rel or "_只读拉取" in rel:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm = fm_of(text)
        if fm is None:
            continue
        cur = status_of(fm)
        if cur != "已废止":
            continue
        # ① 目标：GB 8978-1996 那份
        if all(s in rel for s in FIX["must"]) and not any(s in rel for s in FIX["must_not"]):
            fix_hits.append({"path": p, "rel": rel, "cur": cur})
            continue
        # ② 同类嫌疑：自己标着已废止，但路径里出现「部分代替/部分废止」
        if SUSPECT.search(rel):
            suspects.append({"rel": rel, "cur": cur})

    print("=" * 96)
    print("[①] 要改的（官方登记为现行，只是被『部分代替』）")
    for h in fix_hits:
        print("   · %s" % h["rel"])
        print("     status: %s → %s" % (h["cur"], FIX["new"]))
    if not fix_hits:
        print("   （没有命中：可能已经改过）")

    print("=" * 96)
    print("[②] 同类嫌疑（status=已废止，路径里却写着『部分代替』）—— 只报告，不自动改")
    for s in suspects:
        print("   · %s" % s["rel"][:110])
    print("   共 %d 份，需逐条查官方登记后决定" % len(suspects))

    if not args.apply or not fix_hits:
        print("\n（未加 --apply，什么都没改）")
        return 0

    BAK.mkdir(parents=True, exist_ok=True)
    manifest = []
    for h in fix_hits:
        p = h["path"]
        dst = BAK / ("%s.%s" % (p.name, STAMP))
        shutil.copy2(p, dst)
        text = p.read_text(encoding="utf-8")
        fm = fm_of(text)
        new_fm, n1 = re.subn(r"^status:[ \t]*.*$", "status: %s" % FIX["new"], fm, count=1, flags=re.M)
        if re.search(r"^status_note:", new_fm, re.M):
            new_fm, n2 = re.subn(r"^status_note:[ \t]*.*$", "status_note: %s" % FIX["note"],
                                 new_fm, count=1, flags=re.M)
        else:
            new_fm, n2 = new_fm + "\nstatus_note: %s" % FIX["note"], 1
        out = text.replace(fm, new_fm, 1)
        p.write_text(out, encoding="utf-8")
        manifest.append({"rel": h["rel"], "backup": str(dst),
                         "status_lines": n1, "note_lines": n2})
        print("已改 %s（status 行 %d，note 行 %d）" % (p.name, n1, n2))
    mf = BAK / ("_清单_%s.json" % STAMP)
    mf.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n备份清单：%s" % mf)
    print("回滚：按清单把备份拷回原位，再跑 建索引v3.py + 切换索引.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
