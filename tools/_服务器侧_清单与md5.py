#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器侧：列出「属于项目的代码文件」并算 md5；按清单打包。

**每次同步都由本地工具上传这份文件**，所以服务器上不会留旧版本 —— 口径永远跟仓库一致。

用法（在服务器上，由 tools/同步线上到仓库.py 自动调用）：
    python3 _服务器侧_清单与md5.py list
        → 每行输出  <md5>\\t<md5去掉CR后的>\\t<相对路径>   （相对 /，例如 home/test/xishu_qingyu_serve/...）
          第二列用于判定"只差行尾"，本地据此不报假更新。

    python3 _服务器侧_清单与md5.py pack <清单文件> <输出.tar.gz>
        → 把清单里列出的文件打成一个 tar.gz（本地解包后按字节写盘）

排除的东西（与仓库口径一致，改这里就要同步改 README 的「不入库清单」）：
    venv/.venv_tools、__pycache__、node_modules、.git
    向量索引 index/ 及其备份、语料 okf_bundles*/、eia_reports_raw/、guides_pdf/
    审核/生成结果与缓存（_cache*、_审核结果、_生成结果）、日志与 pid
    各类 .bak_*/.bak_before_*/.bak_p*、部署前备份目录、_staging、_raw*
    SKIP_REL 里逐个点名的文件（有意不公开，见那里的注释）
"""
from __future__ import annotations

import hashlib
import os
import sys
import tarfile

# 要纳入管理的根（相对 / 的写法）
ROOTS = [
    "home/test/xishu_qingyu_serve",
    "home/test/fagui_serve",
    "data/eia_audit",
    "data/eia_report_gen",
    "data/fagui_rag",
]
# /home/test 下平铺的脚本也纳入（它们在仓库里对应 ops/）
FLAT_DIR = "home/test"

CODE_EXT = (".py", ".sh", ".js", ".mjs", ".css", ".html", ".json", ".md", ".txt",
            ".yml", ".yaml", ".ts", ".vue", ".svg", ".doc", ".docx", ".pdf", ".csv")

SKIP_DIR = {
    "__pycache__", ".venv", ".venv_tools", "venv", "node_modules", ".git", ".idea",
    "index", "okf_bundles", "okf_bundles_stage", "okf_bundles_eia_sample",
    "eia_reports_raw", "guides_pdf", "_staging", "_cache", "_cache_narr", "_cache_intake",
    "_审核结果", "_生成结果", "_导出代码", "_backup_标题修正_20260921",
}
SKIP_DIR_PREFIX = ("index.bak", "okf_bundles.bak", "_backup_", "frontend.bak",
                   "xishu_pipeline.bak", "_raw", "_eia_audit_残留", "_同步")
SKIP_FILE_SUFFIX = (".pyc", ".log", ".pid", ".tar.gz", ".zip", ".bak", ".orig")

# 按**相对路径**逐个点名排除的文件（不按目录，因为同目录里其它文件要入库）。
#
# 为什么单列这个：`frontend/data/question-bank.json` 是客户拿来评测模型的 **71 道题原文**，
# 只在线上给客户自己用；本仓库是公开的，题目原文一旦推上去、git 历史就撤不回来。
# 所以它不是"漏同步"，是**有意不公开**（2026-09-24 与使用者确认后的决定）。
# 要改题库就直接在服务器上改那个 JSON，改完不用重启 8011（前端按 no-cache 取）。
SKIP_REL = {
    "home/test/xishu_qingyu_serve/frontend/data/question-bank.json",
}


def is_skipped_rel(rel: str) -> bool:
    """相对 / 的路径是否在不公开名单里（自测 tools/自测_同步工具.py 会调它）。"""
    return rel in SKIP_REL


def skip_dir(name: str) -> bool:
    return name in SKIP_DIR or name.startswith(SKIP_DIR_PREFIX)


def skip_file(name: str) -> bool:
    if name.startswith(".") and name != ".env.example":
        return True
    if name.endswith(SKIP_FILE_SUFFIX):
        return True
    return ".bak_before_" in name or ".bak_p" in name


def md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def md5_lf(path: str) -> str:
    """把 CRLF 归一成 LF 后的 md5。

    用途：本地仓库按 .gitattributes 统一存 LF，线上个别文件是 CRLF，
    直接比 md5 会天天报"内容不同"。用这个值判定"只差行尾"，不算改。
    """
    h = hashlib.md5()
    with open(path, "rb") as fh:
        data = fh.read()
    h.update(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return h.hexdigest()


def collect() -> list:
    """→ [相对路径, ...]（已排序、去重）"""
    out = set()
    for root in ROOTS:
        absroot = "/" + root
        if not os.path.isdir(absroot):
            continue
        for dp, dns, fns in os.walk(absroot, topdown=True):
            dns[:] = [d for d in dns if not skip_dir(d)]
            for f in fns:
                if not f.endswith(CODE_EXT) or skip_file(f):
                    continue
                rel = os.path.relpath(os.path.join(dp, f), "/")
                if is_skipped_rel(rel):
                    continue
                out.add(rel)
    flat = "/" + FLAT_DIR
    if os.path.isdir(flat):
        for f in os.listdir(flat):
            p = os.path.join(flat, f)
            if os.path.isfile(p) and f.endswith((".py", ".sh")) and not skip_file(f):
                out.add(FLAT_DIR + "/" + f)
    # 索引本体（向量）太大不入库，但**每份索引的 meta.json 要留档** —— 单独捞出来
    for base in ("data/fagui_rag/index", "data/fagui_rag/index_v2",
                 "data/fagui_rag/index_stage", "data/fagui_rag/index_eia_sample",
                 "data/fagui_rag/index_v3"):
        meta = "/%s/meta.json" % base
        if os.path.isfile(meta):
            out.add("%s/meta.json" % base)
    return sorted(out)


def cmd_list() -> int:
    bad = 0
    for rel in collect():
        try:
            print("%s\t%s\t%s" % (md5("/" + rel), md5_lf("/" + rel), rel))
        except OSError as exc:                      # 权限/软链异常不该让整轮同步失败
            bad += 1
            print("!%s\t%s" % (type(exc).__name__, rel), file=sys.stderr)
    if bad:
        print("（有 %d 个文件读不了，已在 stderr 标注）" % bad, file=sys.stderr)
    return 0


def cmd_pack(list_file: str, tar_path: str) -> int:
    rels = [l.strip() for l in open(list_file, encoding="utf-8") if l.strip()]
    os.makedirs(os.path.dirname(tar_path), exist_ok=True)
    n = 0
    with tarfile.open(tar_path, "w:gz") as tf:
        for rel in rels:
            p = "/" + rel
            if os.path.isfile(p):
                tf.add(p, arcname=rel)
                n += 1
    print("打包 %d 个文件 → %s（%.1f KB）" % (n, tar_path, os.path.getsize(tar_path) / 1024))
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    what = sys.argv[1]
    if what == "list":
        return cmd_list()
    if what == "pack" and len(sys.argv) == 4:
        return cmd_pack(sys.argv[2], sys.argv[3])
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
