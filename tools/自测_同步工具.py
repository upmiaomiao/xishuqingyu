#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自测 tools/同步线上到仓库.py 的比对逻辑 —— 用合成清单，不连服务器。

造三种情形各一条：内容不同、线上新增、线上已删，看报告是否恰好识别这三条（不多不少）。
"""
from __future__ import annotations

import hashlib
import io
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
WORK = os.path.join(REPO, "_同步")


def md5(p: str) -> str:
    h = hashlib.md5()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def repo_to_server(rel: str):
    parts = rel.split("/")
    if parts[0] == "server" and len(parts) > 1:
        return "/".join(parts[1:])
    if parts[0] == "ops" and len(parts) == 2:
        return "home/test/" + parts[1]
    return None


def main() -> int:
    tracked = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True,
                             encoding="utf-8").stdout.split()
    man = {}
    for rel in tracked:
        srel = repo_to_server(rel)
        if srel:
            man[srel] = md5(os.path.join(REPO, rel))
    if len(man) < 10:
        print("仓库里参与同步的文件太少（%d），自测无意义" % len(man))
        return 2

    keys = sorted(man)
    # ① 改一个（把 md5 改错 → 应识别为"内容不同"）
    victim_mod = next(k for k in keys if k.startswith("data/eia_report_gen/gen/"))
    man[victim_mod] = "0" * 32
    # ② 删一个（从清单里去掉 → 应识别为"线上已删"）。
    #    注意要用 server/** 里的文件：ops/ 下的平铺脚本按策略只提示不自动删，
    #    所以那里造不出"删除"用例（下面单独断言它会落进"保留不动"清单）。
    victim_del = next(k for k in keys if k.startswith("data/eia_audit/") and k.endswith(".py"))
    man.pop(victim_del)
    # ④ 再删一个平铺脚本 → 应落进"ops/ 里线上没有同名的"提示，而不是删除
    victim_orphan = next(k for k in keys
                         if k.startswith("home/test/") and k.count("/") == 2 and k.endswith(".py"))
    man.pop(victim_orphan)
    # ③ 加一个（清单里多一条 → 应识别为"线上新增"）
    fake_new = "home/test/_自测_新脚本.py"
    man[fake_new] = "1" * 32

    os.makedirs(WORK, exist_ok=True)
    path = os.path.join(WORK, "自测清单.txt")
    with io.open(path, "w", encoding="utf-8") as fh:
        for k in sorted(man):
            fh.write("%s\t%s\n" % (man[k], k))

    r = subprocess.run([sys.executable, os.path.join(HERE, "同步线上到仓库.py"),
                        "--manifest", path], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = r.stdout
    print(out)

    checks = [
        ("内容不同（更新）1 个", "识别出 1 个更新"),
        ("线上新增（取回）1 个", "识别出 1 个新增"),
        ("线上已删（仓库移除）1 个", "识别出 1 个删除"),
        (victim_mod, "更新项指向正确的文件"),
        ("ops/_自测_新脚本.py", "新增项指向正确的文件"),
        ("ops/" + victim_orphan.split("/")[-1], "平铺脚本缺失落进提示清单"),
    ]
    bad = 0
    print("\n==== 自测结论 ====")
    for needle, desc in checks:
        ok = needle in out
        bad += 0 if ok else 1
        print("  %s %s（找 %r）" % ("✅" if ok else "❌", desc, needle))
    # 不能把 ops/ 里的本地工具误判成"删除"
    n_del_line = [l for l in out.splitlines() if l.startswith("  线上已删（仓库移除）")]
    if n_del_line and "1 个" not in n_del_line[0]:
        bad += 1
        print("  ❌ 删除条数不对：%s" % n_del_line[0])
    print("\n%s" % ("✅ 自测全部通过" if not bad else "❌ 有 %d 项不符" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
