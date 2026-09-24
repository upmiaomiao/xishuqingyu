#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A 档上线状态核验：文件 md5、判据表 4 条软-待核的判定路径、站点健康。

只读，不改任何东西。跑法（服务器上）：
  EIA_CRITERIA_DIR=/data/fagui_rag/criteria PYTHONPATH=/data/eia_audit:/data/eia_report_gen \
  AUDIT_HOME=/data/eia_audit python3 核验A档上线.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request

FILES = [
    ("/data/eia_audit/audit/criteria.py", "2dc244a69f24b3c4585bb13507808711"),
    ("/data/eia_audit/audit/items_extra.py", "9d156ae73b8a58d5f05d92c8a65f62a2"),
    ("/data/eia_report_gen/gen/decide.py", "28478d58eee8c3c71f73e054773c9605"),
    ("/data/eia_report_gen/gen/narrate.py", "dd16b00075d7e10621b284fe347f1677"),
    ("/data/eia_report_gen/gen/docx_writer.py", "7ff0fc371b09f5e5e288c97e4d5ec507"),
    ("/data/fagui_rag/criteria/标准现行性.json", "3fe85ea1fc1b4e866974bcef5697b309"),
]


def md5(p: str) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    bad = 0
    print("==== 1) 六个文件与工作区源文件是否一致 ====")
    for p, want in FILES:
        if not os.path.isfile(p):
            print("  ❌ 不存在：%s" % p)
            bad += 1
            continue
        got = md5(p)
        ok = got == want
        bad += 0 if ok else 1
        print("  %s %-52s %s" % ("✅" if ok else "❌", os.path.basename(p), got))
        if not ok:
            print("      期望 %s" % want)

    print("\n==== 2) 判据表内容 ====")
    d = json.load(open("/data/fagui_rag/criteria/标准现行性.json", encoding="utf-8"))
    rows = d.get("条目") or []
    by = {}
    for e in rows:
        by[str(e.get("依据硬度"))] = by.get(str(e.get("依据硬度")), 0) + 1
    print("  条目 %d 条；按硬度：%s；生成时间 %s" % (len(rows), by, d.get("生成时间")))
    soft = [e for e in rows if str(e.get("依据硬度")) == "软-待核"]
    print("  软-待核 %d 条：%s" % (len(soft), [e.get("标准号") for e in soft]))

    print("\n==== 3) 4 条软-待核在审核项里的实际判定 ====")
    sys.path.insert(0, "/data/eia_audit")
    import re
    from audit.items_extra import _norm_std, _std_table, _std_validity

    class FakeRep:
        def __init__(self, cites):
            self.cites = cites

        def search(self, rx, max_hits=0, ctx=0):
            out = []
            for pg, sn in self.cites:
                hit = rx.search(sn) if hasattr(rx, "search") else re.search(rx, sn)
                if hit:
                    out.append({"page": pg, "snippet": sn})
            return out[:max_hits] if max_hits else out

    t = _std_table()
    print("  判据表装入：%s（%d 个标准号，更新于 %s）"
          % (t["_meta"]["装入"], t["_meta"].get("标准数"), t["_meta"].get("更新于")))
    for e in soft:
        no = str(e.get("标准号") or "")
        key = _norm_std(no)
        in_tab = key in t
        rows2, _ = _std_validity(FakeRep([(4, "本项目执行 %s 的规定。" % no)]))
        concl = rows2[0]["结论"] if rows2 else "（未命中）"
        ok = in_tab and rows2 and ("未核实" in concl) and ("已被" not in concl)
        bad += 0 if ok else 1
        print("  %s %-16s 命中=%s → %s" % ("✅" if ok else "❌", no, in_tab, concl[:70]))

    print("\n==== 4) 站点健康 ====")
    for path in ("/health", "/audit/api/health", "/gen/api/health"):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8011" + path, timeout=60) as r:
                body = r.read().decode("utf-8", "ignore")
            print("  ✅ %-18s %s" % (path, body[:110]))
        except Exception as exc:                                # noqa: BLE001
            print("  ❌ %-18s %s" % (path, exc))
            bad += 1
    print("\n==== 结论：%s ====" % ("全部核验通过" if not bad else "有 %d 处不通过" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
