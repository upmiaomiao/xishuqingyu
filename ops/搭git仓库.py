#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把服务器导出的代码包整理成 git 仓库目录（server/ 保持线上路径 + ops/ 放运维脚本）。

为什么这么排：
  · `server/` 下**保持线上的绝对路径结构**（server/home/test/... 、server/data/...），
    这样重新部署就是 `cp -r server/home/test/* /home/test/`，不会出现"文件该放哪"的歧义；
  · 273 个散装运维/测试脚本平铺到 `ops/`（它们在线上本来就在 /home/test 平铺）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys


def force_rmtree(path: str) -> bool:
    """先常规删，失败再走 cmd 的 rmdir /s /q（解压残留可能是只读目录）。"""
    if not os.path.isdir(path):
        return True
    for attempt in (1, 2):
        try:
            shutil.rmtree(path)
            return True
        except OSError as exc:
            print("     （第 %d 次常规删除失败：%s）" % (attempt, type(exc).__name__))
            subprocess.run(["cmd", "/c", "attrib", "-R", "/S", "/D", path + r"\*"],
                           capture_output=True)
            subprocess.run(["cmd", "/c", "rmdir", "/s", "/q", path], capture_output=True)
    return not os.path.isdir(path)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "xishuqingyu"))
RAW = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(REPO, "_staging", "raw")

MOVE_DIRS = [
    ("home/test/xishu_qingyu_serve", "server/home/test/xishu_qingyu_serve"),
    ("home/test/fagui_serve", "server/home/test/fagui_serve"),
    ("data/eia_audit", "server/data/eia_audit"),
    ("data/eia_report_gen", "server/data/eia_report_gen"),
    ("data/fagui_rag", "server/data/fagui_rag"),
]


def main() -> int:
    if not os.path.isdir(RAW):
        print("❌ 先解压代码包到 %s" % RAW)
        return 2
    n_moved = n_ops = 0
    for src_rel, dst_rel in MOVE_DIRS:
        src, dst = os.path.join(RAW, src_rel), os.path.join(REPO, dst_rel)
        if not os.path.isdir(src):
            print("  ⚠️ 缺 %s" % src_rel)
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isdir(dst) and not force_rmtree(dst):
            print("  ❌ %s 删不掉，跳过" % dst_rel)
            continue
        shutil.move(src, dst)
        cnt = sum(len(f) for _, _, f in os.walk(dst))
        n_moved += cnt
        print("  ✅ %-34s → %-42s %d 个文件" % (src_rel, dst_rel, cnt))

    ops = os.path.join(REPO, "ops")
    os.makedirs(ops, exist_ok=True)
    flat = os.path.join(RAW, "home", "test")
    for f in sorted(os.listdir(flat)) if os.path.isdir(flat) else []:
        p = os.path.join(flat, f)
        if os.path.isfile(p) and f.endswith((".py", ".sh")):
            shutil.move(p, os.path.join(ops, f))
            n_ops += 1
    print("  ✅ 运维/测试脚本 %d 个 → ops/" % n_ops)

    # 收尾：清掉暂存目录（沙箱可能拒删个别只读残留，删不掉不算失败，记下来即可）
    for junk in ("_staging", "_raw2", "_raw3", "_raw4", "_raw5"):
        p = os.path.join(REPO, junk)
        if os.path.isdir(p):
            if force_rmtree(p):
                print("  ✅ 清理 %s" % junk)
            else:
                print("  ⚠️ %s 删不掉 —— 已加进 .gitignore，不影响提交" % junk)
    print("\n合计：服务端代码 %d 个文件 + 运维脚本 %d 个" % (n_moved, n_ops))
    return 0


if __name__ == "__main__":
    sys.exit(main())
