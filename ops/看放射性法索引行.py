#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看《放射性污染防治法》在线上索引里的行：source 路径、status、status_note 到底有没有。只读。"""
from __future__ import annotations

import io
import json
from pathlib import Path

IDX = Path("/data/fagui_rag/index")
SRC_MD = ("/data/fagui_rag/okf_bundles/生态环境法律法规/法律/法律_43/"
          "中华人民共和国放射性污染防治法/中华人民共和国放射性污染防治法.md")


def main() -> int:
    rows = []
    with io.open(IDX / "chunks.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if "放射性污染防治法" in line:
                rows.append(json.loads(line))
    print("含该法字样的行：%d" % len(rows))
    own = [r for r in rows if "法律_43" in str(r.get("source") or "") and "放射性" in str(r.get("source") or "")]
    print("source 指向该法 bundle 的行：%d" % len(own))
    for r in own[:3]:
        print("  · source=%s" % r.get("source"))
        print("    status=%r  status_note=%r" % (r.get("status"), r.get("status_note")))
        print("    title=%r  正文首 60 字=%r" % (r.get("title"), str(r.get("text"))[:60]))
    if not own:
        print("\n没有 source 指向 bundle 的行，看看前 5 行的 source 长什么样：")
        for r in rows[:5]:
            print("  · %s" % r.get("source"))

    print("\n==== bundle front matter 里有没有 status_note ====")
    if Path(SRC_MD).is_file():
        t = io.open(SRC_MD, encoding="utf-8").read()
        for line in t.split("---")[1].splitlines() if t.startswith("---") else []:
            if "status" in line:
                print("  %s" % line.strip())
    else:
        print("  找不到 bundle：%s" % SRC_MD)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
