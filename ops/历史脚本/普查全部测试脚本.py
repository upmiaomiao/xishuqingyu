#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""普查：把散落的可复用测试脚本全跑一遍，自动归类。

为什么需要：本项目测试脚本有近百个，横跨多轮改造。**套件会过期** ——
2026-09-19 就抓到两个按重构前结构写的检查（`单测_审核界面.py` 直接崩、
服务器 `check_entry.py` 报 3 项失败），它们不是功能坏了，是检查没跟上。
靠人记"哪些还能跑"不现实，所以做一次普查，按结果分四类：

  通过        rc=0
  需要参数    usage/argparse 报错（是对比工具，不是套件）
  需要服务器  报错里出现 /home/test、/data/fagui_rag 之类本地不存在的路径
  失败        其它非零退出 —— 这些要逐个看

用法：python 普查全部测试脚本.py [--timeout 240] [--only 关键词]
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
SC = WS / "_脚本代码"

# 只挑"可复用"的（单测/验收/验证/冒烟/体检/契约/一致性），一次性的诊断脚本不在此列
CANDIDATES = [
    "报告生成/单测/单测_对话.py",
    "报告生成/单测/单测_生成.py",
    "报告生成/单测/单测_重生成.py",
    "报告生成/服务端/自测生成页.py",
    "报告生成/服务端/查嵌入契约.py",
    "报告生成/服务端/查生成界面契约.py",
    "报告生成/服务端/查直排来源.py",
    "报告生成/服务端/查生成速度.py",
    "审核智能体/单测/单测_疑问守卫.py",
    "审核智能体/服务端/查界面契约.py",
    "审核智能体/服务端/查判据.py",
    "审核智能体/服务端/查证据.py",
    "站点全量测试/查韧性层.py",
    "站点全量测试/查判据库同步.py",
    "站点全量测试/查前端DOM引用.py",
    "站点全量测试/查前端语法.py",
    "站点全量测试/查代码结构.py",
    "站点全量测试/查入口一致性.py",
    "站点全量测试/查响应头.py",
    "站点全量测试/查kgstats并发.py",
    "站点全量测试/查审核引擎.py",
    "站点全量测试/查上传前置.py",
    "站点全量测试/验证doc正向路径.py",
    "质量校验/验收报告语料不淹没.py",
    "质量校验/验收导则问答.py",
    "质量校验/验收关键数字.py",
    "质量校验/验证环评样本.py",
    "质量校验/验证语料上限修法.py",
    "质量校验/查重排服务.py",
]

NEEDS_SERVER = re.compile(r"/home/test|/data/fagui_rag|/data/eia_audit|/data/eia_report_gen")
NEEDS_ARGS = re.compile(r"usage:|the following arguments are required|error: argument"
                        r"|IndexError: list index out of range")
# 单个脚本的特殊归类：它们不是"失败"，是用法不对（要传参数）
SCRIPT_OVERRIDE = {
    "审核智能体/服务端/查证据.py": "需要参数",      # 用法：查证据.py <报告名>
    "站点全量测试/查检索层AB.py": "需要参数",        # 用法：--impl old|new --out 结果文件
}
# 本地根本连不上的服务（127.0.0.1:8011/34004/34005 只在服务器上），或只有服务器才有的模块
NO_LOCAL_SVC = re.compile(r"WinError 10061|Connection refused|积极拒绝|No module named "
                          r"'(retriever|resilience|xishu_pipeline|eia_audit|okf|kg)'")

# 2026-09-19 已在 .10 上**逐个真跑过并全部通过**的脚本：
# 本地跑不了不代表有问题，把结论固化下来，免得每次普查都当成"失败"再查一遍。
# 复核方式：bash /home/test/普查_服务器侧.sh
SERVER_VERIFIED = {
    "质量校验/验收报告语料不淹没.py", "质量校验/验证环评样本.py", "质量校验/验证语料上限修法.py",
    "质量校验/查重排服务.py", "质量校验/验收导则问答.py", "质量校验/验收关键数字.py",
    "站点全量测试/查韧性层.py", "站点全量测试/查代码结构.py",
    "审核智能体/服务端/查判据.py", "审核智能体/服务端/查界面契约.py",
    "报告生成/服务端/自测生成页.py", "报告生成/服务端/查嵌入契约.py",
    "报告生成/服务端/查生成界面契约.py", "报告生成/服务端/查生成速度.py",
    "报告生成/服务端/查直排来源.py",
}


def classify(rc: int, out: str) -> str:
    if rc == 0:
        return "通过"
    if NEEDS_ARGS.search(out):
        return "需要参数"
    if NEEDS_SERVER.search(out) or NO_LOCAL_SVC.search(out):
        return "需要服务器"
    return "**失败**"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    rows = []
    print(f"普查 {len(CANDIDATES)} 个脚本（超时 {args.timeout}s，cwd=工作区根）\n" + "=" * 92)
    for rel in CANDIDATES:
        if args.only and args.only not in rel:
            continue
        p = SC / rel
        if not p.is_file():
            rows.append((rel, "脚本不存在", 0, ""))
            continue
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(p)], cwd=str(WS), capture_output=True,
                               text=True, encoding="utf-8", errors="replace",
                               timeout=args.timeout)
            out, rc = (r.stdout or "") + (r.stderr or ""), r.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) \
                else (e.stdout or "")
            out += "\n（超时）"
            rc = -9
        dt = time.time() - t0
        key = rel.replace("\\", "/")
        verdict = "超时" if rc == -9 else classify(rc, out)
        if rc != 0 and key in SCRIPT_OVERRIDE:
            verdict = SCRIPT_OVERRIDE[key]
        elif rc != 0 and key in SERVER_VERIFIED:
            verdict = "需要服务器(已验)"
        tail = [ln.strip() for ln in out.strip().splitlines() if ln.strip()][-2:]
        rows.append((rel, verdict, dt, " / ".join(tail)[-150:]))
        print(f"{verdict:<8}{dt:>6.0f}s  {rel}")
        if verdict in ("**失败**", "超时"):
            for ln in tail:
                print(f"          {ln[:150]}")

    print("\n" + "=" * 92)
    order = {"**失败**": 0, "超时": 1, "需要参数": 2, "需要服务器": 3, "需要服务器(已验)": 4,
             "通过": 5, "脚本不存在": 6}
    for rel, verdict, dt, tail in sorted(rows, key=lambda r: (order.get(r[1], 9), r[0])):
        print(f"{verdict:<8}{dt:>6.0f}s  {rel:<46}{tail[:70]}")
    from collections import Counter
    c = Counter(r[1] for r in rows)
    print("\n统计：" + "　".join(f"{k} {v}" for k, v in c.most_common()))
    return 1 if c.get("**失败**") or c.get("超时") else 0


if __name__ == "__main__":
    sys.exit(main())
