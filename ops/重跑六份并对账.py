#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务端：[021] 把"已有审核结果"按当前代码重跑一遍，并逐份与备份对账。

为什么要写成一个脚本而不是手敲 6 次：
  ① 得记录**每份的真实耗时**（用户要"先报耗时"，而结果 JSON 里没有耗时字段）；
  ② 得逐份**逐项**对比，而不是只看统计数字（统计相同不代表内容相同）；
  ③ 对比必须对着**备份**做（重跑会覆盖 `_审核结果/*.json`）。

前置：备份目录 /home/test/_重构归档_20260922/第三批_前/审核结果_重跑前

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 重跑六份并对账.py
"""
from __future__ import annotations

import glob
import io
import json
import os
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011/audit"
NEW = "/data/eia_audit/_审核结果"
OLD = "/home/test/_重构归档_20260922/第三批_前/审核结果_重跑前"
OUT_JSON = "/home/test/重跑对账.json"


def names() -> list:
    """从备份里取要重跑的报告名（gold评测.json 是评测件，跳过）。"""
    out = []
    for p in sorted(glob.glob(os.path.join(OLD, "*.json"))):
        b = os.path.basename(p)
        if b.startswith("gold"):
            continue
        try:
            d = json.load(io.open(p, encoding="utf-8"))
        except Exception:                                           # noqa: BLE001
            continue
        f = d.get("file") or {}
        nm = f.get("name") if isinstance(f, dict) else str(f)
        if nm and (d.get("items") or []):
            out.append((b, nm))
    return out


def run_one(nm: str) -> dict:
    req = urllib.request.Request(
        BASE + "/api/run?name=" + urllib.parse.quote(nm) + "&use_llm=true", data=b"")
    j = json.load(urllib.request.urlopen(req, timeout=60))
    t0 = time.time()
    for _ in range(1200):                       # 最多等 1 小时
        time.sleep(2)
        s = json.load(urllib.request.urlopen(BASE + "/api/job/" + j["job"], timeout=60))
        if s.get("done"):
            return {"secs": s.get("secs") or round(time.time() - t0, 1),
                    "error": s.get("error"), "统计": (s.get("result") or {}).get("统计")}
    return {"secs": round(time.time() - t0, 1), "error": "等待超时", "统计": None}


def sig(it: dict) -> str:
    return json.dumps(it, ensure_ascii=False, sort_keys=True)


def diff_one(bak: str, new: str) -> dict:
    o = json.load(io.open(os.path.join(OLD, bak), encoding="utf-8"))
    n = json.load(io.open(os.path.join(NEW, new), encoding="utf-8"))
    oi, ni = o.get("items") or [], n.get("items") or []
    ch = []
    for a, b in zip(oi, ni):
        if sig(a) != sig(b):
            ch.append({"审核项": a.get("审核项"),
                       "旧": a.get("AI审核"), "新": b.get("AI审核"),
                       "理由旧": str(a.get("理由"))[:150], "理由新": str(b.get("理由"))[:150]})
    return {"条数旧": len(oi), "条数新": len(ni),
            "统计旧": o.get("统计"), "统计新": n.get("统计"),
            "统计相同": o.get("统计") == n.get("统计"),
            "变化条数": len(ch), "变化": ch}


def main() -> int:
    todo = names()
    print("待重跑：%d 份\n" % len(todo))
    rep = []
    for i, (bak, nm) in enumerate(todo, 1):
        print("[%d/%d] %s" % (i, len(todo), nm))
        r = run_one(nm)
        print("      用时 %ss ｜ 统计 %s%s"
              % (r["secs"], json.dumps(r["统计"], ensure_ascii=False),
                 "  ！！失败：" + str(r["error"]) if r["error"] else ""))
        newf = os.path.basename(bak)
        d = {"报告": nm, "用时s": r["secs"], "错误": r["error"]}
        if not r["error"] and os.path.exists(os.path.join(NEW, newf)):
            d.update(diff_one(bak, newf))
        rep.append(d)
        print("      逐项：一致 %d ／ 变化 %d ｜ 统计相同 %s"
              % (d.get("条数新", 0) - d.get("变化条数", 0), d.get("变化条数", -1), d.get("统计相同")))
        for c in d.get("变化", []):
            print("        · %s：%s → %s" % (c["审核项"], c["旧"], c["新"]))

    io.open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1))
    tot = sum(x["用时s"] or 0 for x in rep)
    chg = sum(x.get("变化条数", 0) for x in rep)
    print("\n" + "=" * 70)
    print("重跑 %d 份，总耗时 %.1fs；判定有变化的条目共 %d 条" % (len(rep), tot, chg))
    print("对账明细：%s" % OUT_JSON)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
