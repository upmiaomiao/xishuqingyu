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
# 被测工具的输出走管道，默认按控制台编码（cp936）编码 —— 这里统一按 UTF-8 收
ENV_UTF8 = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")


def run_tool(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, os.path.join(HERE, "同步线上到仓库.py"), *argv],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", env=ENV_UTF8)


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

    r = run_tool("--manifest", path)
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

    # ---- 编码回归：2026-09-24 真机踩到的坑 ----
    # helper（本机 Python）按 cp936 输出，这边按 UTF-8 解 → 中文路径变 U+FFFD，
    # 比对静默错成「仓库里一堆文件线上没了、线上又新增一堆」。两道防线都要测。
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "sync_tool", os.path.join(HERE, "同步线上到仓库.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    print("\n==== 编码回归 ====")
    zh = "ops/查敏感信息.py"
    for enc in ("utf-8", "gbk"):
        ok = mod.decode_out(zh.encode(enc)) == zh
        bad += 0 if ok else 1
        print("  %s 按 %s 输出的字节都能解回原样" % ("✅" if ok else "❌", enc))

    # 清单里出现 U+FFFD 必须中止，而不是报出一堆假的"线上新增"
    bogus = os.path.join(WORK, "自测清单_坏编码.txt")
    io.open(bogus, "w", encoding="utf-8").write(
        "%s\tdata/fagui_rag/criteria/\ufffd\ufffd.json\n" % ("2" * 32))
    r2 = run_tool("--manifest", bogus)
    guard = r2.returncode != 0 and "U+FFFD" in (r2.stdout + r2.stderr)
    fake = "线上新增（取回）" in r2.stdout
    bad += 0 if (guard and not fake) else 1
    print("  %s 坏编码清单被中止、没报假差异" % ("✅" if guard and not fake else "❌"))

    # ---- 不公开名单绊线（2026-09-24）----
    # 题库 JSON 是客户评测题原文，**有意**不进公开仓库（见服务器侧清单工具里的 SKIP_REL）。
    # 这里盯住那条排除规则：万一被谁顺手删掉，同步就会把 71 道题原文推进公开仓库、
    # 而且 git 历史撤不回来 —— 所以宁可让自测红，也不要静默推上去。
    spec2 = importlib.util.spec_from_file_location(
        "srv_list", os.path.join(HERE, "_服务器侧_清单与md5.py"))
    m2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(m2)
    print("\n==== 不公开名单 ====")
    bank = "home/test/xishu_qingyu_serve/frontend/data/question-bank.json"
    c1 = m2.is_skipped_rel(bank)
    bad += 0 if c1 else 1
    print("  %s 题库 JSON 在不公开名单里" % ("✅" if c1 else "❌"))
    # 反向对照：判定函数不能恒真，同目录的代码文件必须照常入库
    other = "home/test/xishu_qingyu_serve/frontend/js/questions.js"
    c2 = not m2.is_skipped_rel(other)
    bad += 0 if c2 else 1
    print("  %s 同目录的代码文件照常入库（反向对照）" % ("✅" if c2 else "❌"))

    print("\n%s" % ("✅ 自测全部通过" if not bad else "❌ 有 %d 项不符" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
