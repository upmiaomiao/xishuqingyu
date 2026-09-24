#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把挑出来的 20 条垃圾焚烧题拿到**线上站点**实跑，看 RAG 路线下的真实效果。

只看客观可自动判的东西（主观打分留给人工/judge）：
  · 是否答出、耗时、答案长度
  · 引用条数与构成：依据类（标准规范/法律法规/环评导则）vs 案例类（环评报告）
  · 题目里的**标准号**（GB/HJ/DB/HG…）有没有被引到、有没有出现在答案里
  · 是否出现"未提供/未涉及/材料中未给出"这类**回避表述**
  · 答案里的具体数值个数（数值多≠好，但要看到底有没有数字）

用法：python 验20条_线上实跑.py [--only 序号,序号]
输出：_工作记录/实跑20条_输出.jsonl（含完整答案与来源）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
IN = WS / "_工作记录" / "垃圾焚烧好题型20条.jsonl"
OUT = WS / "_工作记录" / "实跑20条_输出.jsonl"
BASE = "http://10.201.31.10:8011"
AUTH_DIRS = ("生态环境标准规范", "生态环境法律法规", "环评导则")

RE_STD = re.compile(r"\b(GB|HJ|DB\d{2}|HG|JB|CJJ|CJ|NY|DL)\s*/?\s*[TZ]?\s*\d{2,5}(?:[.—-]\d{2,4})?", re.I)
RE_AVOID = re.compile(r"未提供|未给出|未涉及|未明确|没有给出|材料中未|无从|无法确定|未包含")
RE_NUM = re.compile(r"\d+(?:\.\d+)?")


def load(p: Path):
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ask(q: str, timeout: int = 900) -> dict:
    req = urllib.request.Request(
        BASE + "/hybrid_search",
        data=json.dumps({"query": q}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def stds_in(text: str) -> set[str]:
    return {" ".join(m.group(0).split()).upper().replace("—", "-").replace("－", "-")
            for m in RE_STD.finditer(text or "")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None

    items = [r for r in load(IN) if only is None or r["序号"] in only]
    print(f"实跑 {len(items)} 条 → {BASE}/hybrid_search\n" + "=" * 100)
    rows = []
    for it in items:
        q = it["题目"]
        t0 = time.time()
        try:
            d = ask(q)
            err = ""
        except urllib.error.HTTPError as e:
            d, err = {}, f"HTTP {e.code}"
        except Exception as e:  # noqa: BLE001
            d, err = {}, f"{type(e).__name__}: {e}"
        dt = time.time() - t0
        ans = d.get("answer") or ""
        srcs = d.get("sources") or []
        auth = [s for s in srcs if (s.get("source") or "").split("/")[0] in AUTH_DIRS]
        q_std = stds_in(q)
        cited_std = set()
        for s in srcs:
            cited_std |= stds_in(s.get("source") or "")
        rec = {
            "序号": it["序号"], "题型": it["题型"], "语言": it.get("语言", "中文"),
            "题目": q, "来源": it["来源"],
            "error": err, "耗时s": round(dt, 1), "route": d.get("route"),
            "答案": ans, "答案字数": len(ans),
            "引用条数": len(srcs), "依据类条数": len(auth),
            "引用来源": [s.get("source") for s in srcs],
            "题目中的标准号": sorted(q_std),
            "引用里命中的标准号": sorted(q_std & cited_std),
            "答案里命中的标准号": sorted(q_std & stds_in(ans)),
            "回避表述": len(RE_AVOID.findall(ans)),
            "数值个数": len(RE_NUM.findall(ans)),
            "有think": "<think>" in ans,
        }
        rows.append(rec)
        flag = "✅" if not err else "❌"
        print(f"{flag} [{it['序号']:>2}] {it['题型'][:12]:<12} {dt:>5.0f}s  "
              f"答案 {len(ans):>5} 字  引用 {len(srcs):>2}（依据 {len(auth):>2}）  "
              f"标准号命中 {len(rec['引用里命中的标准号'])}/{len(q_std)}  "
              f"回避 {rec['回避表述']}  数值 {rec['数值个数']}  {err}")

    OUT.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    print("\n" + "=" * 100)
    ok = [r for r in rows if not r["error"]]
    print(f"成功 {len(ok)}/{len(rows)}　平均耗时 "
          f"{sum(r['耗时s'] for r in ok)/max(1,len(ok)):.0f}s　"
          f"平均引用 {sum(r['引用条数'] for r in ok)/max(1,len(ok)):.1f} 条　"
          f"平均答案 {sum(r['答案字数'] for r in ok)/max(1,len(ok)):.0f} 字")
    print(f"完整输出 → {OUT.relative_to(WS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
