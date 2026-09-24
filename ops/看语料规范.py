#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看语料库的规范：front matter 字段、PDF 存放约定、附件目录长什么样。

用途：B4 要把《太湖地区城镇污水处理厂及重点工业行业主要水污染物排放限值》
(DB32/1072-2018) 作为**标准本体**入库，得先照着现有标准的格式来，别自创字段。
"""
from __future__ import annotations

import io
import re
from collections import Counter
from pathlib import Path

BUNDLE = Path("/data/fagui_rag/okf_bundles")


def fm_of(t: str) -> str:
    m = re.match(r"^---\s*\n(.*?)\n---", t, re.S)
    return m.group(1) if m else ""


def main() -> int:
    # 1) 找一份"标准本体"样例（储油库 GB 20950—2020）
    cands = [p for p in BUNDLE.rglob("*.md") if "储油库大气污染物排放标准" in p.name]
    print("样例候选 %d 份；取带 2020 的那份：" % len(cands))
    sample = next((p for p in cands if "2020" in p.name), cands[0] if cands else None)
    if sample:
        print("  路径：%s" % sample.relative_to(BUNDLE))
        t = io.open(sample, encoding="utf-8", errors="replace").read()
        print("  ---- front matter ----")
        for ln in fm_of(t).splitlines():
            print("   %s" % ln[:120])
        print("  ---- 正文开头 200 字 ----")
        print("   %s" % re.sub(r"\s+", " ", t[:900])[-260:])

    # 2) source_path 都指到哪
    pref = Counter()
    n = 0
    for p in BUNDLE.rglob("*.md"):
        t = io.open(p, encoding="utf-8", errors="replace").read(1200)
        m = re.search(r"^source_path:\s*(.+)$", t, re.M)
        if m:
            n += 1
            s = m.group(1).strip()
            pref["/".join(s.split("/")[:3])] += 1
    print("\nsource_path 出现 %d 份；前缀分布前 6：" % n)
    for k, v in pref.most_common(6):
        print("   %5d  %s" % (v, k))

    # 3) 标准目录下常见文件名（看有没有 _附件 之类）
    if sample:
        d = sample.parent
        print("\n样例所在目录：%s" % d.relative_to(BUNDLE))
        for p in sorted(d.iterdir())[:8]:
            print("   %s %s" % ("[目录]" if p.is_dir() else "      ", p.name[:90]))
        for p in sorted(d.parent.iterdir())[:6]:
            print("   上级： %s %s" % ("[目录]" if p.is_dir() else "      ", p.name[:84]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
