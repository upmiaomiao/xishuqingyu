#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署源与线上文件到底差在哪 —— 覆盖之前先看清楚，别把新的覆盖成旧的。

对每一对（本地部署源 / 线上已部署文件）打印：
  行数对比、差异块数、前几个差异块的摘要。
"""
from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

import paramiko

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
sys.path.insert(0, str(WS / "服务器会话"))
from rsh import parse_creds  # noqa: E402

PAIRS = [
    ("_脚本代码/审核智能体/服务端/audit_routes.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/audit_routes.py"),
    ("_脚本代码/审核智能体/服务端/audit.html",
     "/home/test/xishu_qingyu_serve/frontend/audit.html"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js"),
    ("_脚本代码/报告生成/服务端/gen_routes.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py"),
    ("_脚本代码/报告生成/服务端/gen.html",
     "/home/test/xishu_qingyu_serve/frontend/gen.html"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css"),
    ("服务器会话/服务端/rag/ingest_okf.py", "/data/fagui_rag/ingest_okf.py"),
]

user, pw = parse_creds(str(WS / "账号.md"))["10.201.31.10"]
cli = paramiko.SSHClient()
cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
cli.connect("10.201.31.10", 22, user, pw, timeout=20, look_for_keys=False, allow_agent=False)
sftp = cli.open_sftp()

out_dir = WS / "_中间产物" / "线上源码"
for rel, rem in PAIRS:
    local = WS / rel
    with sftp.open(rem, "rb") as fh:
        raw = fh.read()
    # 存一份线上原件（证据）
    (out_dir / (local.name + "_线上")).write_bytes(raw)
    live = raw.decode("utf-8", "replace").replace("\r\n", "\n").splitlines()
    mine = local.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").splitlines()
    print("=" * 96)
    print(f"【{local.name}】")
    print(f"  本地 {len(mine)} 行 / {local.stat().st_size} 字节　线上 {len(live)} 行 / {len(raw)} 字节")
    sm = difflib.SequenceMatcher(None, mine, live, autojunk=False)
    print(f"  相似度 {sm.ratio():.4f}")
    hunks = [op for op in sm.get_opcodes() if op[0] != "equal"]
    print(f"  差异块 {len(hunks)} 处")
    for tag, i1, i2, j1, j2 in hunks[:4]:
        if tag == "replace":
            print(f"    · 本地 {i1+1}-{i2} 行 ↔ 线上 {j1+1}-{j2} 行（各 {i2-i1} / {j2-j1} 行）")
            for ln in mine[i1:i1 + 2]:
                print(f"        本地| {ln.strip()[:96]}")
            for ln in live[j1:j1 + 2]:
                print(f"        线上| {ln.strip()[:96]}")
        elif tag == "delete":
            print(f"    · 本地 {i1+1}-{i2} 行是线上没有的（{i2-i1} 行）：")
            for ln in mine[i1:i1 + 3]:
                print(f"        本地| {ln.strip()[:96]}")
        else:
            print(f"    · 线上 {j1+1}-{j2} 行是本地没有的（{j2-j1} 行）：")
            for ln in live[j1:j1 + 3]:
                print(f"        线上| {ln.strip()[:96]}")
sftp.close()
cli.close()
