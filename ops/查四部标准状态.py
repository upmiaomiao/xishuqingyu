#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""只读：查这四部标准在库里的 status/status_note，与官方平台结论对照。

2026-09-22 用户交办第 3 件：「可以搜搜，找不到就算了」—— 4 部缺官方来源的标准。
官方平台结论（已查到，见下方 OFFICIAL）：
  GB 9137-1988  废止（被 GB 3095-2012 全部代替）
  GB 20998-2007 废止（2018-07-01 废止；被 GB 18176-2016 部分代替）
  HJ/T 240-2005 现行（备案号 80353-2021）
  HJ/T 241-2005 现行（备案号 80354-2021）
顺带把 GB 8978 与 HJ 915 也打出来做对照。

用法：/home/test/fagui_serve/.venv/bin/python 查四部标准状态.py
"""
from __future__ import annotations

import io
import re
from pathlib import Path

BUNDLE = Path("/data/fagui_rag/okf_bundles")

OFFICIAL = {
    "GB 9137": "废止（被 GB 3095-2012 全部代替）",
    "GB 20998": "废止（2018-07-01 废止，被 GB 18176-2016 部分代替）",
    "HJ/T 240": "现行（备案 80353-2021）",
    "HJ/T 241": "现行（备案 80354-2021）",
    "GB 8978": "现行（仅 GB 20425/20426 部分代替）",
    "HJ 915": "部分代替（库内曾标废止，口径待定）",
}

PAT = {c: re.compile(re.escape(c).replace(r"\ ", r"\s*") + r"[\s—\-]*\d{2,4}", re.I) for c in OFFICIAL}


def fm_of(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    return m.group(1) if m else ""


def field(fm: str, key: str) -> str:
    m = re.search(r"^%s:[ \t]*(.*)$" % key, fm, re.M)
    return (m.group(1) or "").strip() if m else ""


def main() -> int:
    hits = {c: [] for c in OFFICIAL}
    n = 0
    for p in sorted(BUNDLE.rglob("*.md")):
        n += 1
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:                                           # noqa: BLE001
            continue
        head = t[:4000]
        for c, rx in PAT.items():
            if rx.search(head) or rx.search(p.name):
                fm = fm_of(t)
                hits[c].append((str(p.relative_to(BUNDLE)), field(fm, "title")[:52],
                                field(fm, "status") or "(无)", field(fm, "status_note")[:70]))
    print("扫描 bundle：%d 份\n" % n)
    for c, rows in hits.items():
        print("=" * 88)
        print("%s ｜ 官方：%s ｜ 命中 %d 份" % (c, OFFICIAL[c], len(rows)))
        for rel, title, st, note in rows[:8]:
            flag = ""
            off_abol = OFFICIAL[c].startswith("废止")
            if off_abol and st not in ("已废止", "废止"):
                flag = "   ← 与官方不一致！"
            if not off_abol and st in ("已废止", "废止"):
                flag = "   ← 与官方不一致！"
            print("   · %s" % rel)
            print("       title=%s ｜ status=%s%s" % (title, st, flag))
            if note:
                print("       status_note=%s" % note)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
