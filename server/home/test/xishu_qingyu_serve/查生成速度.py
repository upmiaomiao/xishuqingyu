#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成速度与"是不是预设"的实测（诊断用，不改任何东西）。

回答两个问题：
  ① 为什么点了很快就出报告？ —— 拆开计时：抽事实 / 生成任务 / 各阶段日志时间戳，
     并统计 _cache_narr 缓存条数（缓存命中 = 没调模型）。
  ② 内容是不是预设的？ —— 用**同一段描述**连跑两次，比较 docx 的 md5：
     一样 → 说明是"同输入同输出"（可复现，不是预设）；再换一段**新的**描述跑一次，
     md5 必然不同 → 说明正文是按事实生成的。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查生成速度.py
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011/gen"
# 缓存就在引擎目录下（narrate.py / intake.py 的 CACHE_DIR 是 HERE/_cache_*，
# HERE = gen/）—— 第一版我指到了上一层，于是统计出 0 条，差点得出错误结论。
GEN = "/data/eia_report_gen/gen"
NARR = os.path.join(GEN, "_cache_narr")
INTAKE = os.path.join(GEN, "_cache_intake")
OUTDIR = "/data/eia_report_gen/_生成结果"


def post(path: str, body: dict) -> dict:
    # 注意：接口都在 /gen/api 下，这里统一补 /api（之前漏过，直接 404）
    req = urllib.request.Request(BASE + "/api" + path, data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def get(path: str):
    with urllib.request.urlopen(BASE + "/api" + path, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def nfiles(d: str) -> int:
    return len(glob.glob(os.path.join(d, "*.json")))


def run(desc: str, label: str) -> dict:
    """走一遍：抽事实 → 生成 → 轮询到终态。返回耗时与产物信息。

    同时报告**缓存是否命中**（看 _cache_narr 条数有没有增长）—— 否则单看耗时会被
    "上一条描述刚好把缓存热了"这种情况带偏（第一版就被示例轮换搅乱过读数）。
    """
    n0, i0 = nfiles(NARR), nfiles(INTAKE)
    t0 = time.time()
    st = post("/chat/start", {"text": desc})
    sid = st["session"]
    t1 = time.time()
    jid = post("/chat/generate", {"session": sid, "model": True})["job"]
    last = None
    while True:
        time.sleep(1)
        last = get("/job/" + jid)["job"]
        if last["status"] in ("done", "rejected", "failed"):
            break
        if time.time() - t0 > 600:
            break
    t2 = time.time()
    n1, i1 = nfiles(NARR), nfiles(INTAKE)
    print("\n【%s】" % label)
    print("  抽事实（含模型抽取）：%5.1f 秒" % (t1 - t0))
    print("  生成到终态：        %5.1f 秒" % (t2 - t1))
    print("  合计：              %5.1f 秒" % (t2 - t0))
    print("  叙述缓存 %d → %d：%s" % (n0, n1, "未命中（真调了模型）" if n1 > n0 else "命中（没调模型）"))
    print("  抽取缓存 %d → %d：%s" % (i0, i1, "未命中" if i1 > i0 else "命中"))
    for l in (last.get("log") or [])[:3]:
        print("    [%s] %s" % (l["step"], l["text"][:100]))
    # job 里的字段叫 file（第一版我写了 name → 拿不到文件名 → md5 全是 None，
    # "md5 相同/不同"的结论也就全是空的：None == None）
    fname = last.get("file") or ""
    out = os.path.join(OUTDIR, fname)
    md5 = None
    if fname and os.path.isfile(out):
        md5 = hashlib.md5(open(out, "rb").read()).hexdigest()
    print("  产物：%s  %s 字节  md5=%s" % (fname, last.get("size"), md5))
    return {"md5": md5, "size": last.get("size"), "秒": round(t2 - t0, 1),
            "抽事实秒": round(t1 - t0, 1), "命中": n1 == n0}


NEW_TEXT = ("【虚构示例】某机械加工厂新增 8 台数控机床，年加工金属件 5000 吨，"
            "总投资 800 万元，环保投资 30 万元，用地 2000 平方米。切削液循环使用不外排，"
            "金属废屑外售综合利用，厂界南侧 150 米是李家村约 60 户 210 人，项目尚未开工。")


def main() -> int:
    demo = get("/chat/demo")["示例"]
    print("=" * 66)
    print("示例文本（本次抽到的一条）：", demo[:56], "…")
    print("缓存条数：_cache_narr=%d  _cache_intake=%d" % (nfiles(NARR), nfiles(INTAKE)))

    # 同一段描述连跑两次：第一次可能冷/热，第二次必命中 —— 这样"缓存"这件事才说得清
    a = run(demo, "① 示例文本 第 1 次")
    b = run(demo, "② 示例文本 第 2 次（应命中缓存）")
    c = run(NEW_TEXT, "③ 全新描述 第 1 次（多半未命中）")
    d = run(NEW_TEXT, "④ 全新描述 第 2 次（应命中缓存）")

    print("\n" + "=" * 66)
    print("结论：")
    print("  同描述两次 md5 %s（%s）" % (
        "相同" if a["md5"] == b["md5"] else "不同",
        "同输入同输出 = 可复现，不是预设" if a["md5"] == b["md5"] else "不该不同，需查"))
    print("  换描述 md5 %s（%s）" % (
        "不同" if a["md5"] != c["md5"] else "相同",
        "换描述就换报告 = 正文按事实生成" if a["md5"] != c["md5"] else "可疑！"))
    print("  同描述两次（新）md5 %s" % ("相同" if c["md5"] == d["md5"] else "不同"))
    print("  耗时：示例 %s / %s 秒，新描述 %s / %s 秒" % (a["秒"], b["秒"], c["秒"], d["秒"]))
    print("  缓存命中情况：示例 %s→%s，新描述 %s→%s（True=命中=没调模型）" % (
        a["命中"], b["命中"], c["命中"], d["命中"]))
    print("  缓存条数：_cache_narr=%d  _cache_intake=%d" % (nfiles(NARR), nfiles(INTAKE)))
    return 0


if __name__ == "__main__":
    sys.exit(main())