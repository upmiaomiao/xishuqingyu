#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索层零回归 A/B：同一索引下只切「标准号硬命中」开关，重放 20 条好题型的检索。

为什么不是跟 09-21 老基线比（这个坑我踩过一次）：老基线录在**旧索引**上；
09-22 索引做过"标题修正 + 状态改写"重建（标题进嵌入配方，会合法改变检索结果）。
拿它当基线的实测结果是 20 条全变、其中 14 条与标准号毫无关系 —— 那是把索引变更的账
记到检索器头上。正确判据必须在**同一索引**下只切一个开关：

    RAG_STD_PIN=0（等价改动前行为） vs RAG_STD_PIN=1（线上默认）
      · 题面**不含**标准号的题 —— 引用集合必须逐条完全一致（一条都不许变）
      · 题面**含**标准号的题 —— 允许变化，且应"多出该标准原文"而非"丢掉原有依据"

只跑检索、不调模型：便宜、快，且直接测被改的那一层。
用法：python 回归_检索层.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WS = HERE                                       # 脚本在工作区 _脚本代码/站点全量测试/ 下
BASE = os.path.join(WS, "_工作记录", "实跑20条_输出v2.jsonl")
HOST = "10.201.31.10"
PUT = os.path.join(WS, "服务器会话", "put_file.py")
RUN = os.path.join(WS, "服务器会话", "runcmd.py")
GET = os.path.join(WS, "服务器会话", "get_file.py")
OUT_JSON = os.path.join(WS, "_工作记录", "回归_检索层结果.json")
RE_CODE = re.compile(r"(GB|HJ|DB)\s*/?\s*T?\s*\d{2,5}", re.I)


def sh(args: list) -> str:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-800:])
        raise SystemExit("失败：%s" % args[1])
    return (r.stdout or "") + (r.stderr or "")


def find_question(obj: dict) -> str:
    for k in ("题目", "question", "q", "问题", "query", "题面"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def find_sources(obj: dict) -> list:
    """从基线记录里抠出引用清单（title/source 都留，便于宽松比对）。"""
    for k in ("引用", "sources", "citations", "refs"):
        v = obj.get(k)
        if isinstance(v, list) and v:
            out = []
            for s in v:
                if isinstance(s, dict):
                    out.append((s.get("title") or "").strip() or (s.get("source") or "").strip())
                elif isinstance(s, str):
                    out.append(s.strip())
            return [x for x in out if x]
    return []


def main() -> int:
    items = []
    with open(BASE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            q = find_question(o)
            if q:
                codes = o.get("题目中的标准号") or []
                items.append({"q": q, "old_base": find_sources(o),
                              "has_code": bool(codes) or bool(RE_CODE.search(q))})
    print("题目：%d 条（题面含标准号 %d 条）｜含标准号的允许变化，其余必须逐条一致"
          % (len(items), sum(1 for i in items if i["has_code"])))
    if not items:
        raise SystemExit("基线里没解析出题目，先看字段名")

    payload = os.path.join(WS, "_中间产物", "回归_检索层_题目.json")
    os.makedirs(os.path.dirname(payload), exist_ok=True)
    with open(payload, "w", encoding="utf-8") as f:
        json.dump([{"q": i["q"], "has_code": i["has_code"]} for i in items], f,
                  ensure_ascii=False, indent=1)
    print(sh([PUT, "--host", HOST, payload, "/home/test/回归_检索层_题目.json"]).strip()[:150])
    print(sh([PUT, "--host", HOST,
              os.path.join(HERE, "_脚本代码", "服务器运维", "回归_检索层重放.py"),
              "/home/test/回归_检索层重放.py"]).strip()[:150])

    arms = {}
    for arm, env in (("off", "RAG_STD_PIN=0"), ("on", "RAG_STD_PIN=1")):
        t0 = time.time()
        print(sh([RUN, "--host", HOST, "--timeout", "2400",
                  "cd /home/test && %s /home/test/fagui_serve/.venv/bin/python "
                  "回归_检索层重放.py %s 2>&1 | tail -3" % (env, arm)]).strip())
        print("  臂 %s 用时 %.1f 分钟" % (arm, (time.time() - t0) / 60))
        local = os.path.join(WS, "_工作记录", "_回归_检索层_%s.json" % arm)
        sh([GET, "--host", HOST, "/home/test/回归_检索层_结果_%s.json" % arm, local])
        arms[arm] = json.load(open(local, encoding="utf-8"))

    same = diff = 0
    bad, rows = [], []
    for it, off, on in zip(items, arms["off"], arms["on"]):
        a, b = off.get("now") or [], on.get("now") or []
        lost = [x for x in a if x not in b]
        gained = [x for x in b if x not in a]
        if a == b:
            same += 1
            rows.append({**it, "verdict": "一致"})
        else:
            diff += 1
            v = "变化（含标准号，允许）" if it["has_code"] else "**不一致（不该变）**"
            if not it["has_code"]:
                bad.append({"q": it["q"], "lost": lost, "gained": gained})
            rows.append({**it, "lost": lost, "gained": gained, "verdict": v})

    print("\n" + "=" * 96)
    for r in rows:
        if r["verdict"] == "一致":
            continue
        print("【%s】%s" % (r["verdict"], r["q"][:62]))
        for x in (r.get("lost") or [])[:3]:
            print("    - 丢：%s" % x[:74])
        for x in (r.get("gained") or [])[:3]:
            print("    + 增：%s" % x[:74])
    print("=" * 96)
    print("两臂引用完全一致 %d 条 ｜ 有变化 %d 条 ｜ **题面不含标准号却变化：%d 条**"
          % (same, diff, len(bad)))
    print("结论：%s" % ("✅ 零回归（关掉开关即回到改动前行为，且只在含标准号时生效）"
                       if not bad else "❌ 有附带影响，需排查"))
    json.dump({"at": time.strftime("%Y-%m-%d %H:%M:%S"), "一致": same, "变化": diff,
               "题面不含标准号却变化": bad, "rows": rows},
              open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("明细：%s" % OUT_JSON)
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
