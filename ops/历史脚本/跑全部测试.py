#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一把跑完成套测试（本地侧），输出总表 + 每套的尾部输出。

为什么要它：套件有十几个，散在各个目录，每次手动跑容易漏；
而且"哪些套件本来就跑不了（服务器侧脚本）"也需要写清楚，免得把环境问题当成回归。

★ 2026-09-19 修正三处（第一次写的时候自己踩的）：
  ① **cwd**：套件里写的是相对路径（`_中间产物/重构工作区/frontend`），必须从**工作区根**跑；
     我原来用脚本所在目录当 cwd，结果 `前端快检.py` 报 FileNotFoundError ——
     **那是跑测脚本的毛病，不是回归**，差点误报。
  ② **分类**：`查清洗影响面.py`、`查邻块扩展.py` 里写死了 `/home/test`、`/data/fagui_rag`，
     只能在服务器上跑 → 移出本地清单（否则每次"失败"都是噪音）。
  ③ `查检索层AB.py` 是要带 `--impl/--out` 的对比工具，不是通过/失败套件 → 也移出清单。

用法：
  python 跑全部测试.py                  # 站点侧 8 套
  python 跑全部测试.py --含审核          # 再跑审核智能体 4 个单测 + 7 份端到端
  python 跑全部测试.py --快              # 只跑 1 分钟内的
  python 跑全部测试.py --only 全面测试
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent          # _脚本代码/站点全量测试/
WS = HERE.parents[1]                            # 工作区根
AUDIT = WS / "_脚本代码" / "审核智能体"

# (分组, 名称, 脚本相对路径, 超时秒, 是否快套件, 运行目录)
SUITES = [
    ("站点", "全面测试_站点", "全面测试_站点.py", 2400, False, HERE),
    ("站点", "线上验收探针", "线上验收探针.py", 900, False, HERE),
    ("站点", "验收死链止血", "验收死链止血.py", 600, True, HERE),
    ("站点", "错误码验证", "错误码验证.py", 900, False, HERE),
    ("站点", "即时冒烟", "即时冒烟.py", 900, False, HERE),
    ("站点", "前端快检", "前端快检.py", 600, True, HERE),
    ("站点", "查检索层工具函数", "查检索层工具函数.py", 600, True, HERE),
    ("站点", "查文本清洗", "查文本清洗.py", 600, True, HERE),
    ("审核", "单测_判据层", "单测/单测_判据层.py", 600, True, AUDIT),
    ("审核", "单测_防编造", "单测/单测_防编造.py", 600, True, AUDIT),
    ("审核", "单测_十八项", "单测/单测_十八项.py", 600, True, AUDIT),
    ("审核", "单测_审核界面", "单测/单测_审核界面.py", 600, True, AUDIT),
    ("审核", "审核_报告(7份端到端)", "审核_报告.py --all", 3600, False, AUDIT),
]

# 写死了服务器路径，只能在 .10 上用 venv python 跑 —— 单列出来，别当成失败
SERVER_ONLY = [
    "查P6表格是否上线.py", "规范合规体检.py", "查二噁英表格.py",
    "查清洗影响面.py", "查邻块扩展.py",
    "查LaTeX对检索的影响.py", "查LaTeX对重排的影响.py",
    "建归一索引.py", "建归一索引_预检.py", "建归一索引_复现配方.py",
    "查归一漏写.py", "查归一后数值块.py", "查重排批次效应.py",
]
NEEDS_ARGS = ["查检索层AB.py（要 --impl old|new --out 结果文件，是对比工具不是套件）"]


def find_script(rel: str) -> Path:
    """按名字找脚本：先在指定目录找，找不到就在 _脚本代码 下按文件名找（套件常被挪窝）。"""
    name = rel.split()[0]
    for base in (HERE, AUDIT, WS / "_脚本代码"):
        p = base / name
        if p.is_file():
            return p
        hits = list(base.rglob(Path(name).name))
        if hits:
            return hits[0]
    return HERE / name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--快", action="store_true", help="只跑快套件")
    ap.add_argument("--含审核", action="store_true", help="连审核智能体的单测与端到端一起跑")
    ap.add_argument("--only", default="", help="只跑名字里含这个词的")
    args = ap.parse_args()

    todo = [(g, n, s, t, c) for g, n, s, t, fast, c in SUITES
            if (args.含审核 or g == "站点")
            and (not args.快 or fast)
            and (not args.only or args.only in n)]
    print(f"套件 {len(todo)} 个（工作区根 {WS}）\n" + "=" * 92)
    rows = []
    for group, name, spec, timeout, cwd in todo:
        parts = spec.split()
        p = find_script(spec)
        if not p.is_file():
            rows.append((group, name, "缺失", 0, f"{spec} 不存在"))
            print(f"❓ {name}: 脚本不存在 {spec}")
            continue
        t0 = time.time()
        try:
            r = subprocess.run([sys.executable, str(p)] + parts[1:], cwd=str(WS),
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=timeout)
            out, rc = (r.stdout or "") + (r.stderr or ""), r.returncode
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) \
                else (e.stdout or "")
            rc = -9
        dt = time.time() - t0
        tail = [ln for ln in out.strip().splitlines() if ln.strip()][-3:]
        verdict = "通过" if rc == 0 else f"**失败(rc={rc})**"
        rows.append((group, name, verdict, dt, " / ".join(x.strip() for x in tail)[-160:]))
        print(f"\n【{group}·{name}】{verdict}　{dt:.0f}s")
        for ln in tail:
            print(f"    {ln.strip()[:160]}")

    print("\n" + "=" * 92)
    print(f"{'套件':<24}{'结果':<16}{'耗时':>7}  尾部输出")
    for group, name, verdict, dt, tail in rows:
        print(f"{group}·{name:<20}{verdict:<16}{dt:>6.0f}s  {tail[:88]}")
    bad = [r for r in rows if r[2] != "通过"]
    print(f"\n合计 {len(rows)} 套：通过 {len(rows)-len(bad)}，失败 {len(bad)}")
    if bad:
        print("失败清单：", "、".join(f"{r[0]}·{r[1]}" for r in bad))
    print("\n（下面这些写死服务器路径，只能在 .10 上用 /home/test/fagui_serve/.venv/bin/python 跑，未纳入本表：）")
    print("  " + "、".join(SERVER_ONLY))
    print("（需带参数、不属于通过/失败套件的：）")
    print("  " + "；".join(NEEDS_ARGS))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
