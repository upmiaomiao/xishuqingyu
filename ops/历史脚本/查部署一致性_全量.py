#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地源码树 vs 服务器已部署文件的**全量**一致性比对（不止几个关键文件）。

为什么需要：项目把 `服务器会话/xishu_site/` 写成"服务端权威源码树"，README 里的部署
方式就是把它拷到服务器。一旦镜像比线上旧，照文档部署一次就会**把线上功能覆盖掉**。

口径：本地按 LF 归一化后算 md5（put_file.py 上传时会把 CRLF 转 LF），
与服务器 md5sum 比。这样 Windows 工作区的行尾差异不会被误报成"不一致"。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MIRROR = os.path.join(ROOT, "服务器会话", "xishu_site")
REMOTE = "/home/test/xishu_qingyu_serve"
RUNC = os.path.join(ROOT, "服务器会话", "runcmd.py")

# 本地镜像相对路径 → 服务器相对路径（前缀不同，所以逐条映射）
PAIRS = []
for sub in ("xishu_pipeline",):
    d = os.path.join(MIRROR, sub)
    for n in sorted(os.listdir(d)):
        if n.endswith(".py"):
            PAIRS.append(("%s/%s" % (sub, n), "%s/%s" % (sub, n)))
for n in sorted(os.listdir(os.path.join(MIRROR, "frontend"))):
    if n.endswith(".html"):
        PAIRS.append(("frontend/%s" % n, "frontend/%s" % n))
PAIRS.append(("xishu_qingyu_qa.py", "xishu_qingyu_qa.py"))

# 服务端物：本地在别处，服务器在 xishu_pipeline/ 下
EXTRA = [
    ("_脚本代码/审核智能体/服务端/audit_routes.py", "xishu_pipeline/audit_routes.py"),
    ("_脚本代码/审核智能体/服务端/audit.html", "frontend/audit.html"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.js", "xishu_pipeline/static/audit_ui.js"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.css", "xishu_pipeline/static/audit_ui.css"),
    ("_脚本代码/报告生成/服务端/gen_routes.py", "xishu_pipeline/gen_routes.py"),
    ("_脚本代码/报告生成/服务端/gen.html", "frontend/gen.html"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.js", "xishu_pipeline/static/gen_ui.js"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.css", "xishu_pipeline/static/gen_ui.css"),
]


def md5lf(p: str) -> str:
    with open(p, "rb") as f:
        return hashlib.md5(f.read().replace(b"\r\n", b"\n")).hexdigest()


def main() -> int:
    allpairs = [(os.path.join(MIRROR, a.replace("/", os.sep)), b) for a, b in PAIRS]
    allpairs += [(os.path.join(ROOT, a.replace("/", os.sep)), b) for a, b in EXTRA]

    remotes = " ".join(REMOTE + "/" + b for _, b in allpairs)
    out = subprocess.run([sys.executable, RUNC, "--host", "10.201.31.10", "md5sum " + remotes],
                         capture_output=True, text=True, encoding="utf-8", errors="replace")
    server = {}
    for line in (out.stdout or "").splitlines():
        parts = line.split()
        if len(parts) == 2 and len(parts[0]) == 32:
            server[parts[1]] = parts[0]

    same, diff, missing = [], [], []
    for local, remote in allpairs:
        rpath = REMOTE + "/" + remote
        if not os.path.isfile(local):
            missing.append((local, remote, "本地缺"))
            continue
        if rpath not in server:
            missing.append((local, remote, "服务器缺"))
            continue
        a, b = md5lf(local), server[rpath]
        (same if a == b else diff).append((local, remote, a, b))

    print("比对 %d 个文件：一致 %d / **不一致 %d** / 缺失 %d\n" % (len(allpairs), len(same), len(diff), len(missing)))
    if diff:
        print("== 不一致（本地镜像 ≠ 线上）==")
        for local, remote, a, b in diff:
            print("  %-52s 本地 %s  线上 %s" % (remote, a[:12], b[:12]))
            print("      本地文件：%s" % os.path.relpath(local, ROOT))
    if missing:
        print("\n== 缺失 ==")
        for local, remote, why in missing:
            print("  %-52s %s" % (remote, why))
    if not diff and not missing:
        print("全部一致 ✓")
    return 1 if (diff or missing) else 0


if __name__ == "__main__":
    sys.exit(main())
