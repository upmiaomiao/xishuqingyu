#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库本地 vs 服务器逐条比对：到底哪边新、差在什么内容上。"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUNC = os.path.join(ROOT, "服务器会话", "runcmd.py")
TMP = os.path.join(ROOT, "_中间产物", "_crit_server")

PAIRS = [
    ("判据库/环境风险判据.json", "/data/fagui_rag/criteria/环境风险判据.json"),
    ("判据库/专项评价设置判据.json", "/data/fagui_rag/criteria/专项评价设置判据.json"),
    ("判据库/分类管理名录2021.json", "/data/fagui_rag/criteria/分类管理名录2021.json"),
    ("判据库/有毒有害大气污染物名录2018.json",
     "/data/fagui_rag/criteria/有毒有害大气污染物名录2018.json"),
    ("判据库/报告表结构.json", "/data/eia_report_gen/判据库/报告表结构.json"),
    ("判据库/标准引用清单.json", "/data/eia_report_gen/判据库/标准引用清单.json"),
]


def get(remote: str, local: str) -> bool:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "服务器会话", "get_file.py"),
                        remote, local], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return os.path.isfile(local)


def walk(o, path=""):
    """把 JSON 摊平成 {路径: 值}，便于逐条比对。"""
    if isinstance(o, dict):
        for k, v in o.items():
            yield from walk(v, "%s/%s" % (path, k))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, "%s[%d]" % (path, i))
    else:
        yield path, o


def main() -> int:
    os.makedirs(TMP, exist_ok=True)
    bad = 0
    for local_rel, remote in PAIRS:
        lp = os.path.join(ROOT, local_rel.replace("/", os.sep))
        sp = os.path.join(TMP, os.path.basename(local_rel))
        print("=" * 78)
        print("%s" % local_rel)
        if not os.path.isfile(lp):
            print("  本地缺失")
            bad += 1
            continue
        if not get(remote, sp):
            print("  服务器取不到：%s" % remote)
            bad += 1
            continue
        a = open(lp, "rb").read()
        b = open(sp, "rb").read()
        # ★ 检查器自己踩的第三个坑：直接比字节会把"CRLF vs LF"报成内容不同。
        # 本项目 3 个判据文件正是这种情况（字节差恰好等于行数：2599 / 248 / 6679），
        # 内容其实逐条相同。口径必须与 查部署一致性_全量.py 一致：LF 归一化后再比。
        ma, mb = hashlib.md5(a.replace(b"\r\n", b"\n")).hexdigest(), \
                 hashlib.md5(b.replace(b"\r\n", b"\n")).hexdigest()
        print("  本地 %d 字节 md5(LF)=%s" % (len(a), ma))
        print("  线上 %d 字节 md5(LF)=%s" % (len(b), mb))
        if ma == mb:
            print("  → 一致 ✓（原始字节 %s）" % ("相同" if a == b else "只差行尾 CRLF/LF"))
            continue
        bad += 1
        try:
            ja, jb = json.loads(a.decode("utf-8")), json.loads(b.decode("utf-8"))
        except Exception as e:                                 # noqa: BLE001
            print("  → 内容不同，且不是合法 JSON 可比对：%s" % e)
            continue
        fa, fb = dict(walk(ja)), dict(walk(jb))
        only_local = [k for k in fa if k not in fb]
        only_serv = [k for k in fb if k not in fa]
        changed = [k for k in fa if k in fb and fa[k] != fb[k]]
        print("  → **不一致**：本地独有 %d 条 / 线上独有 %d 条 / 同路径值不同 %d 条"
              % (len(only_local), len(only_serv), len(changed)))
        if isinstance(ja, dict) and isinstance(jb, dict):
            print("     顶层键  本地 %d 个 / 线上 %d 个" % (len(ja), len(jb)))
        for k in only_local[:6]:
            print("     本地独有: %s = %s" % (k[:90], str(fa[k])[:60]))
        for k in only_serv[:6]:
            print("     线上独有: %s = %s" % (k[:90], str(fb[k])[:60]))
        for k in changed[:6]:
            print("     值不同  : %s  本地=%s  线上=%s" % (k[:70], str(fa[k])[:40], str(fb[k])[:40]))
    print("\n" + "=" * 78)
    print("不一致/缺失的文件数：%d / %d" % (bad, len(PAIRS)))
    return bad


if __name__ == "__main__":
    sys.exit(main())
