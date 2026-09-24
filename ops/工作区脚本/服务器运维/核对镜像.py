#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""核对本地副本与服务器线上文件是否一致 —— 一条命令看清"哪些本地文件是旧的"。

为什么需要它：
  本项目踩过两次坑 —— 本地镜像滞后，照着改了半天，改的是旧版
  （RAG 的 retriever.py、站点的 routes.py 各一次）。
  本地同一份文件最多有 7 个副本，靠肉眼分辨"哪份是线上那份"不现实。

判定分四级（关键：**换行符不同不算内容不一致**，Windows 上拷贝极易带上 CRLF）：
  ✅ 一致          内容与换行符都相同
  ～ 仅换行符不同   内容相同（可直接当线上原件阅读/复制，但别拿它的 md5 去比对线上）
  ❌ 内容不一致     本地是旧版（或本地改过没部署）—— **直接给出下载命令**
  ➕/➖ 多出/缺失   本地有线上没有 / 线上有本地没有（镜像不完整）

用法：
  python 核对镜像.py            # 只报告
  python 核对镜像.py --sync     # 报告后，把"不一致/缺失"的从线上重新拉下来
"""
from __future__ import annotations

import argparse
import hashlib
import os
import posixpath
import shutil
import sys
from pathlib import Path

import paramiko

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]                      # 工作区根
sys.path.insert(0, str(WS / "服务器会话"))
from rsh import parse_creds  # noqa: E402

# 本地目录 → 线上目录（本地目录下按相对路径对应线上）
ROOTS = [
    (WS / "服务器会话" / "xishu_site", "/home/test/xishu_qingyu_serve"),
    (WS / "_中间产物" / "重构工作区", "/home/test/xishu_qingyu_serve"),
    (WS / "_脚本代码" / "站点全量测试", "/home/test"),
]
EXTS = (".py", ".js", ".html", ".css", ".sh", ".json", ".md")
SKIP_DIRS = ("__pycache__", ".venv", "node_modules", ".git", "logs", "uploads",
             "_语法检查临时", "_mjscheck", "_错误码改动前", "_只读拉取",
             "_备份_20260919", "_前端副本修正_20260918")
# 这些根只关心"同名文件内容是否一致"，本地多出来的文件不算问题
# （测试脚本本来就只在本地跑，不必都传到服务器）
NO_EXTRA_ROOTS = {"站点全量测试"}
# 这些根是"工作集"，不是完整镜像 —— 本地没有某个线上文件不算问题
NO_MISSING_ROOTS = {"重构工作区"}
# 有意与线上不一致的（不是错误，是"本地有未部署的改动"），报告里要写清原因
EXPECTED_DIVERGENCE = {
    "服务器会话/服务端/rag/ingest_okf.py":
        "本地是 P6 的『表格感知切块 + 来源抬头』版（337 行），线上仍是旧的段落切块（269 行）。"
        "已实测：线上索引里储油库标准 75 条块含限值数字 0 条，P6 暂存索引 76 条里有 2 条。"
        "**等重建索引时一并部署**，见 `_工作记录/待确认事项.md [013]`",
}

# 同名不同路径的"部署源 → 线上文件"配对（这些文件各有权威副本，不在镜像树里）
PAIRS = [
    ("_脚本代码/审核智能体/服务端/audit_routes.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/audit_routes.py", "审核接口"),
    # 2026-09-22 新增：原文批注视图的锚定层与前端的视图模块。
    # 教训：这两份新文件当时只放进了站点镜像树，**部署源里没有** ——
    # 部署源的 audit_ui.js 是"权威副本"（见上面对），漏一份，下次从部署源
    # 发一次就把刚上线的批注视图整个盖掉，而且线上看着"正常"，不会报错。
    ("_脚本代码/审核智能体/服务端/audit_anchor.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/audit_anchor.py", "批注锚定层"),
    ("_脚本代码/审核智能体/服务端/static/audit_doc.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_doc.js", "原文批注视图模块"),
    ("_脚本代码/审核智能体/服务端/audit.html",
     "/home/test/xishu_qingyu_serve/frontend/audit.html", "审核独立页"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js", "审核界面模块"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.css", "审核界面样式"),
    ("_脚本代码/审核智能体/服务端/static/audit_page.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_page.js", "审核独立页模块"),
    ("_脚本代码/审核智能体/服务端/static/audit_page.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_page.css", "审核独立页样式"),
    ("_脚本代码/审核智能体/服务端/查入口.py",
     "/data/eia_audit/check_entry.py", "审核入口检查（审核引擎自检）"),
    ("_脚本代码/报告生成/服务端/gen_routes.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py", "生成接口"),
    ("_脚本代码/报告生成/服务端/gen.html",
     "/home/test/xishu_qingyu_serve/frontend/gen.html", "生成独立页"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js", "生成界面模块"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css", "生成界面样式"),
    ("服务器会话/服务端/rag/retriever.py",
     "/data/fagui_rag/retriever.py", "检索层（问答引用谁）"),
    ("服务器会话/服务端/rag/ingest_okf.py",
     "/data/fagui_rag/ingest_okf.py", "入库脚本（嵌入配方在这里）"),
]


def md5_bytes(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def norm(b: bytes) -> bytes:
    """统一成 LF 再比 —— 只关心内容，不关心换行符。"""
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def remote_md5(cli, roots: list[str]) -> dict[str, str]:
    """一次性取回线上所有相关文件的 md5（根路径|相对路径 → md5）"""
    pattern = " -o ".join(f"-name '*{e}'" for e in EXTS)
    parts = []
    for r in roots:
        parts.append(f"cd {r} && find . -maxdepth 6 -type f \\( {pattern} \\) "
                     f"-not -path '*__pycache__*' -not -path '*/.venv/*' "
                     f"-not -path './okf_bundles*' -not -path './eia_reports_raw*' "
                     f"-exec md5sum {{}} + ")
    cmd = " ; ".join(parts)
    _, so, se = cli.exec_command(cmd, timeout=180)
    out = so.read().decode("utf-8", "replace")
    se.read()
    table: dict[str, str] = {}
    for line in out.splitlines():
        line = line.strip()
        if not line or "  " not in line:
            continue
        h, p = line.split("  ", 1)
        p = p.strip()
        if not p.startswith("./"):
            continue
        rel = p[2:]
        for r in roots:
            table.setdefault(f"{r}|{rel}", h)
    return table


def one_md5(cli, paths: list[str]) -> dict[str, str]:
    """按绝对路径取指定文件的 md5（用于 PAIRS）"""
    if not paths:
        return {}
    cmd = "md5sum " + " ".join(paths) + " 2>/dev/null"
    _, so, _ = cli.exec_command(cmd, timeout=60)
    out = so.read().decode("utf-8", "replace")
    got = {}
    for line in out.splitlines():
        if "  " in line:
            h, p = line.split("  ", 1)
            got[p.strip()] = h
    return got


def judge(local: Path, want: str) -> str:
    """ok / eol / diff"""
    b = local.read_bytes()
    if md5_bytes(b) == want:
        return "ok"
    if md5_bytes(norm(b)) == want:
        return "eol"
    return "diff"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="10.201.31.10")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--sync-pairs", action="store_true",
                    help="把『部署源』也按线上刷新（线上是已部署并验收过的版本；覆盖前先备份本地旧版）")
    args = ap.parse_args()

    user, pw = parse_creds(str(WS / "账号.md"))[args.host]
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(args.host, 22, user, pw, timeout=20, look_for_keys=False, allow_agent=False)

    remote = remote_md5(cli, sorted({r for _, r in ROOTS}))
    print(f"线上收录 {len(remote)} 个压缩范围内的文件\n")

    stat = {"ok": 0, "eol": 0, "diff": 0, "extra": 0, "missing": 0}
    bad: list[tuple[Path, str]] = []          # 需要重新拉的文件
    for local_root, remote_root in ROOTS:
        if not local_root.is_dir():
            continue
        print("=" * 92)
        print(f"【{local_root.relative_to(WS)}】 ↔ {remote_root}")
        rows = []
        seen = set()
        for p in sorted(local_root.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in EXTS:
                continue
            if any(s in p.parts for s in SKIP_DIRS):
                continue
            rel = p.relative_to(local_root).as_posix()
            seen.add(rel)
            key = f"{remote_root}|{rel}"
            if key not in remote:
                if local_root.name not in NO_EXTRA_ROOTS:
                    rows.append(("➕", rel, "本地多出（线上没有这个文件）"))
                    stat["extra"] += 1
                continue
            v = judge(p, remote[key])
            if v == "ok":
                stat["ok"] += 1
            elif v == "eol":
                stat["eol"] += 1
                rows.append(("～", rel, "仅换行符不同（内容与线上一致）"))
            else:
                stat["diff"] += 1
                rows.append(("❌", rel, "内容与线上不一致 —— 本地是旧版或改动未部署"))
                bad.append((p, f"{remote_root}/{rel}"))
        # 线上有、本地没有
        prefix = f"{remote_root}|"
        subdirs = {d.name for d in local_root.iterdir() if d.is_dir()}
        for k in remote:
            if k.startswith(prefix):
                rel = k[len(prefix):]
                if rel not in seen and rel.split("/")[0] in subdirs:
                    stat["missing"] += 1
                    rows.append(("➖", rel, "线上有、本地缺（镜像不完整）"))
                    if local_root.name not in NO_MISSING_ROOTS:
                        bad.append((local_root / rel, f"{remote_root}/{rel}"))
        for mark, rel, why in rows:
            print(f"  {mark} {rel}")
            print(f"      {why}")

    # ---------- 部署源 → 线上 ----------
    print("\n" + "=" * 92)
    print("【部署源 ↔ 线上已部署文件】（这些文件各有权威副本，不在镜像树里）")
    pairs = one_md5(cli, [rem for _, rem, _ in PAIRS])
    _, so, _ = cli.exec_command(
        "stat -c '%n %Y' " + " ".join(rem for _, rem, _ in PAIRS) + " 2>/dev/null", timeout=60)
    remote_mtime = {}
    for line in so.read().decode("utf-8", "replace").splitlines():
        if " " in line:
            p, t = line.rsplit(" ", 1)
            remote_mtime[p] = float(t)
    p_ok = p_eol = p_bad = p_known = 0
    for rel, rem, label in PAIRS:
        local = WS / rel
        if not local.is_file():
            print(f"  ❓ {label}: 本地缺 {rel}")
            p_bad += 1
            continue
        if rem not in pairs:
            print(f"  ❓ {label}: 线上缺 {rem}")
            p_bad += 1
            continue
        v = judge(local, pairs[rem])
        if v == "ok":
            p_ok += 1
            print(f"  ✅ {label}: 双方一致")
        elif v == "eol":
            p_eol += 1
            print(f"  ～ {label}: 仅换行符不同（上传会自动转 LF，属正常）")
        elif rel in EXPECTED_DIVERGENCE or rel.replace("\\", "/") in EXPECTED_DIVERGENCE:
            p_known += 1
            print(f"  ⚠️ {label}: 有意不一致（本地有未部署的改动，不是错误）")
            print(f"      {EXPECTED_DIVERGENCE[rel.replace(chr(92), '/')]}")
        else:
            p_bad += 1
            nl = len(local.read_text(encoding="utf-8", errors="replace")
                     .replace("\r\n", "\n").splitlines())
            print(f"  ❌ {label}: 内容不一致（本地 {nl} 行）—— 方向要看清，别盲目覆盖：")
            print(f"       python _脚本代码/服务器运维/比对部署源与线上.py")
            print(f"      本地 {rel}")
            print(f"      线上 {rem}")

    print("\n" + "=" * 92)
    print(f"镜像树：一致 {stat['ok']}　仅换行符不同 {stat['eol']}　"
          f"**内容不一致 {stat['diff']}**　本地多出 {stat['extra']}　本地缺失 {stat['missing']}")
    print(f"部署源：一致 {p_ok}　仅换行符不同 {p_eol}　**不一致 {p_bad}**　有意不一致 {p_known}")

    if args.sync and bad:
        sftp = cli.open_sftp()
        print(f"\n开始同步镜像树 {len(bad)} 个文件（以线上为准，写回本地）…")
        for local, rem in bad:
            local.parent.mkdir(parents=True, exist_ok=True)
            with sftp.open(rem, "rb") as fh:
                data = fh.read()
            local.write_bytes(data)          # 原样字节，不转 CRLF
            print(f"  已更新 {local.relative_to(WS)}  ←  {rem}  ({len(data)} 字节)")
        sftp.close()
    elif bad:
        print("\n（加 --sync 可把这些文件按线上原样拉回本地）")
        for local, rem in bad[:8]:
            print(f"   python 服务器会话/get_file.py --host {args.host} {rem} \"{local.relative_to(WS)}\"")

    if args.sync_pairs:
        arch = WS / "_中间产物" / "_归档_旧快照_20260919" / "部署源_覆盖前"
        arch.mkdir(parents=True, exist_ok=True)
        sftp = cli.open_sftp()
        print(f"\n刷新部署源（以线上为准；本地旧版先备份到 {arch.relative_to(WS)}）…")
        n = 0
        for rel, rem, label in PAIRS:
            if rel.replace("\\", "/") in EXPECTED_DIVERGENCE:
                print(f"  跳过 {label}（有意不一致，等重建索引时再动）")
                continue
            local = WS / rel
            try:
                with sftp.open(rem, "rb") as fh:
                    data = fh.read()
            except Exception as e:
                print(f"  跳过 {label}：读线上失败 {e}")
                continue
            if local.is_file() and judge(local, md5_bytes(data)) == "ok":
                continue
            if local.is_file():
                shutil.copy2(local, arch / f"{local.name}.旧_20260919")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(data)
            n += 1
            print(f"  已刷新 {rel}  ←  {rem}（{len(data)} 字节，旧版已备份）")
        sftp.close()
        print(f"部署源共刷新 {n} 个")
    cli.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
