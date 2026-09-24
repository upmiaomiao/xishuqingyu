#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重写仓库的 .gitignore 为 UTF-8 + LF，并诊断"为什么忽略规则没生效"。

背景：早先用 PowerShell 的 Add-Content 追加过几段，结果文件变成非法 UTF-8，
且追加行是 CRLF —— git 解析 .gitignore 时会把 \\r 当成模式的一部分，规则就废了。
"""
from __future__ import annotations

import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "xishuqingyu"))
IGN = os.path.join(REPO, ".gitignore")

CONTENT = """# ---- 运行期产物 / 缓存，不入库 ----
__pycache__/
*.py[cod]
*.so
.venv/
.venv_tools/
venv/
node_modules/
*.log
*.pid
_cache/
_cache_*/
_cache_intake/
_cache_narr/
_审核结果/
_生成结果/
_导出代码/

# ---- 大数据：语料、向量索引、PDF、备份 ----
index/
index.bak*/
okf_bundles/
okf_bundles*/
eia_reports_raw/
guides_pdf/
_staging/
_backup_标题修正_*/
*.tar.gz
*.zip

# ---- 备份文件（部署前留的，线上有、仓库不要）----
*.bak_before_*
*.bak_p[0-9]_*
*.bak_*
*_残留*/
*.orig
*~

# ---- 密钥：只提交 .env.example ----
.env
.env.*
!.env.example

# ---- 核对产物（本地跑核对脚本时生成，不是代码）----
_线上*.txt
_*清单.txt
/_meta/

# ---- 本地临时 ----
_raw*/
*.tmp
Thumbs.db
.DS_Store
"""


def main() -> int:
    old = b""
    if os.path.isfile(IGN):
        old = open(IGN, "rb").read()
    print("重写前：%d 字节；含 CRLF？%s；UTF-8 可解码？%s"
          % (len(old), b"\r\n" in old, _try(old)))

    with open(IGN, "wb") as fh:
        fh.write(CONTENT.encode("utf-8"))
    new = open(IGN, "rb").read()
    print("重写后：%d 字节；含 CRLF？%s；UTF-8 可解码？%s"
          % (len(new), b"\r\n" in new, _try(new)))

    for target in ("_服务器代码清单.txt", "_线上md5.txt", ".env", "ops/体检.sh"):
        r = subprocess.run(["git", "-C", REPO, "check-ignore", "-v", target],
                           capture_output=True, text=True, encoding="utf-8")
        print("  %-22s → %s" % (target, (r.stdout.strip() or "未被忽略（会入库！）")))
    return 0


def _try(blob: bytes) -> str:
    try:
        blob.decode("utf-8")
        return "是"
    except UnicodeDecodeError:
        return "否（非法 UTF-8）"


if __name__ == "__main__":
    raise SystemExit(main())
