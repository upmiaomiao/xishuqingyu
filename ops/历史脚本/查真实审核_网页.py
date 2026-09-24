#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""走网页 API 跑一次**真实审核**（use_llm=true），并验两次跑结果是否字节一致。

为什么单独写：既有 `审核_报告.py --all` 走的是引擎 CLI，不是网页这条路；
而网页这条路多了"后台线程 + job 轮询 + 落盘 + 导出"四段，要单独验。
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011/audit"
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:160]) if detail else ""))


def req(method, path, data=None, timeout=60):
    url = BASE + path
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    h = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), round(time.time() - t0, 2)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 2)
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode(), round(time.time() - t0, 2)


def J(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return None


def run_once(name, use_llm, label, budget=900):
    st, b, _ = req("POST", "/api/run?name=%s&use_llm=%s"
                   % (urllib.parse.quote(name), "true" if use_llm else "false"))
    d = J(b) or {}
    if st != 200 or not d.get("job"):
        return None, "提交失败 HTTP %s %s" % (st, b[:120])
    job = d["job"]
    t0 = time.time()
    last = ""
    while time.time() - t0 < budget:
        st, b, _ = req("GET", "/api/job/" + job, timeout=30)
        j = J(b) or {}
        last = "%s %s%%" % (j.get("stage"), j.get("pct"))
        if j.get("done"):
            return j, round(time.time() - t0, 1)
        time.sleep(3)
    return None, "超时（最后阶段 %s）" % last


def canon(res: dict) -> str:
    """去掉易变的元信息后做规范化 JSON，用于比对两次跑是否一致。"""
    r = {k: v for k, v in (res or {}).items() if k not in ("secs", "耗时", "时间")}
    return json.dumps(r, ensure_ascii=False, sort_keys=True)


def main() -> int:
    print("目标：%s" % BASE)
    st, b, _ = req("GET", "/api/reports")
    reps = (J(b) or {}).get("reports") or []
    if not reps:
        print("拿不到报告清单，退出")
        return 1
    name = reps[0]["name"]
    print("测试报告：%s（%d 字节）\n" % (name, reps[0]["size"]))

    print("[1] 第一次跑（use_llm=true，真调模型）")
    j1, t1 = run_once(name, True, "第1次")
    check("第一次跑到 done", isinstance(j1, dict), t1)
    if not isinstance(j1, dict):
        print("  中止：%s" % t1)
        return 1
    res1 = j1.get("result") or {}
    items = res1.get("items") or []
    check("  恰好 18 项审核项", len(items) == 18, "%d 项" % len(items))
    check("  没有 error 字段", not j1.get("error"), str(j1.get("error"))[:120])
    check("  每项都有 序号/审核项/类别/AI审核/理由",
          all(it.get("审核项") and it.get("类别") and it.get("AI审核") is not None
              and it.get("理由") is not None for it in items))
    check("  结论都在允许集合内",
          all(it.get("AI审核") in ("存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用")
              for it in items),
          sorted({it.get("AI审核") for it in items}))
    check("  证据带页码与摘录（至少部分项）",
          any((it.get("证据") or [{}])[0].get("page") for it in items))
    check("  有统计汇总", bool(res1.get("统计")), res1.get("统计"))
    check("  文件信息有页数", bool((res1.get("file") or {}).get("pages")),
          (res1.get("file") or {}).get("pages"))
    print("  结论分布：%s" % json.dumps(res1.get("统计") or {}, ensure_ascii=False))
    print("  用时：%ss" % t1)
    md5_1 = hashlib.md5(canon(res1).encode("utf-8")).hexdigest()
    print("  规范化 md5：%s\n" % md5_1)

    print("[2] 第二次跑同一份（应命中缓存 → 快，且结果一致）")
    j2, t2 = run_once(name, True, "第2次")
    check("第二次跑到 done", isinstance(j2, dict), t2)
    if isinstance(j2, dict):
        res2 = j2.get("result") or {}
        md5_2 = hashlib.md5(canon(res2).encode("utf-8")).hexdigest()
        check("  ★ 两次结果完全一致（可复现）", md5_1 == md5_2, "%s vs %s" % (md5_1[:12], md5_2[:12]))
        # 不断言"第二次更快"：耗时受缓存预热/解析并发影响，属于不稳定断言（第一版这么写，
        # 报了假失败：第一次 0.2s 是因为结果早已缓存，第二次 3.4s 是重解析 PDF）。
        print("  两次用时：%ss / %ss（仅记录，不做快慢断言）\n" % (t1, t2))

    print("[3] 结果落盘与导出")
    st, b, _ = req("GET", "/api/export/%s?fmt=csv" % urllib.parse.quote(name))
    d = J(b) or {}
    check("导出 CSV 成功", st == 200 and bool(d.get("file")), d.get("file"))
    if d.get("file"):
        st, b, _ = req("GET", "/api/download/" + urllib.parse.quote(d["file"]))
        txt = b.decode("utf-8-sig", "replace")
        check("  下载 CSV 成功且带 BOM", st == 200 and b[:3] == b"\xef\xbb\xbf", st)
        # 必须用 csv 解析器数行：理由/证据摘录里含换行，按 splitlines 会多数（第一版就是这么错的）
        import csv as _csv
        import io as _io
        rows = list(_csv.reader(_io.StringIO(txt)))
        rows = [r for r in rows if r and any(c.strip() for c in r)]
        check("  CSV 记录数 = 2 行说明/表头 + 18 项", len(rows) == 20, "%d 条记录" % len(rows))
        check("  CSV 里 18 个审核项都在", all(
            it["审核项"] in txt for it in items))
    st, b, _ = req("GET", "/api/export/%s?fmt=json" % urllib.parse.quote(name))
    d = J(b) or {}
    check("导出 JSON 成功", st == 200 and bool(d.get("file")), d.get("file"))

    print("\n" + "=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for x in BAD:
        print("  × %s" % x)
    return len(BAD)


if __name__ == "__main__":
    sys.exit(main())
