#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C6 时机验证：生成任务跑起来之后，**判定摘要在生成过程中就能拿到**（不是等 done）。

为什么专门验这个：用户反馈「生成过程看不到当前判定」。改法是服务端在②判定一做完就把
`判定` 塞进任务、前端每轮轮询渲染只读卡片。这条契约**只能在运行中观察** ——
跑完之后 `判定` 当然在，那证明不了"过程中可见"；所以这个探针边跑边记：
  · 第一次在轮询里看到 `判定` 时，任务状态还是不是 running？
  · 那一刻距离任务开始多久、总用时多久（即"提前了多少"）？
顺带做一次**生成全流程回归**（改过 gen_routes.py，必须确认还能出 Word）。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 验判定摘要时机.py [--no-model]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011/gen/api"
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:110]) if detail else ""))


def req(method: str, path: str, data=None, timeout=600):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    r = urllib.request.Request(BASE + path, data=body, method=method,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    use_model = "--no-model" not in sys.argv
    desc = ("【判定时机测试】某公司拟建一条年产 3000 吨塑料制品生产线，属于新建项目，"
            "总投资 900 万元，其中环保投资 60 万元，用地面积 2500 平方米。"
            "注塑工序产生有机废气，经集气罩收集后由活性炭吸附装置处理，15 米排气筒排放。"
            "厂界西侧 200 米为红星村，约 80 户 260 人。生活污水经化粪池后排入市政管网，"
            "冷却水循环使用不外排。项目尚未开工建设。")

    print("[1] 起一个会话（真调模型抽取）")
    d = req("POST", "/chat/start", {"text": desc}, timeout=300)
    sid = d.get("session")
    check("拿到会话", bool(sid), sid)
    if not sid:
        return 1
    qs = d.get("问题") or []
    print("     已知事实 %d 项；问题 %d 个" % (len(d.get("已知") or []), len(qs)))

    print("[2] 提交生成任务")
    g = req("POST", "/chat/generate", {"session": sid, "model": use_model})
    job = g.get("job")
    check("拿到任务号", bool(job), job)
    if not job:
        return 1
    t0 = time.time()

    print("[3] 边跑边轮询：判定什么时候出现、那时任务是什么状态")
    first_dec = None          # (秒, 当时状态, 判定里的档级)
    done = None
    last = {}
    for _ in range(1200):                      # 最多等 10 分钟
        try:
            j = (req("GET", "/job/" + job) or {}).get("job") or {}
        except Exception as e:                 # noqa: BLE001
            print("     轮询异常：%s" % e)
            break
        last = j
        if j.get("判定") and first_dec is None:
            first_dec = (time.time() - t0, j.get("status"),
                         (j["判定"].get("名录") or {}).get("tier"),
                         len(j.get("log") or []))
            print("     首次看到「判定」：%.1fs　状态=%s　档级=%s　日志 %d 行"
                  % first_dec)
        if j.get("status") in ("done", "rejected", "failed"):
            done = (time.time() - t0, j.get("status"))
            break
        time.sleep(1.0)

    print("[4] 断言")
    check("任务跑到了终态", done is not None, done)
    check("过程中就拿到过「判定」（不是等 done）", first_dec is not None,
          ("%.1fs" % first_dec[0]) if first_dec else "整轮都没出现过")
    if first_dec and done:
        check("首次出现判定时任务**还在跑**（status=running）", first_dec[1] == "running",
              first_dec[1])
        check("判定早于结束（提前 %.1fs 可见）" % (done[0] - first_dec[0]),
              first_dec[0] < done[0])
        check("判定出现时还没生成完（进度 < 100）", first_dec[3] < 900, "%d 行日志" % first_dec[3])
    if done:
        check("最终状态是 done", done[1] == "done", done[1])
        if done[1] == "done":
            check("有产物文件", bool(last.get("file")), last.get("file"))
            check("判定里有名录档级", bool((last.get("判定") or {}).get("名录")),
                  (last.get("判定") or {}).get("名录"))
            check("判定里有专项评价要素", bool(((last.get("判定") or {}).get("专项评价") or {})
                                          .get("要素")),
                  len(((last.get("判定") or {}).get("专项评价") or {}).get("要素") or []))
    print("[5] 收尾：清掉测试会话与产物")
    try:
        resp = req("POST", "/chat/reset", {"session": sid})
        check("会话已清理", resp.get("已清理") is True, resp)
    except Exception as e:                     # noqa: BLE001
        check("会话已清理", False, e)

    print("=" * 62)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())
