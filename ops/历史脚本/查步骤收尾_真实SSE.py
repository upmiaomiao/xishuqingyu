#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按**前端的步骤合并规则**判定 run/done 是否配平。

为什么重写：上一版在数原始事件，于是
    vision   run=2 done=1      （先"读取图片"、再"等待图片识别完成"，同一阶段报了两次 run）
    generate run=20 done=1     （每 0.8s 报一次已生成字数）
全被判成"缺 done"。但前端 applyStatus 会把**同阶段的连续 run 合并成一步**，
这两条其实都是正常的进度上报 —— 是检查器太天真，不是代码有问题。

真正的判据只有一个：**流结束后，前端的时间线里还有没有停在 running 的步骤。**
所以这里把 applyStatus 的逻辑照抄一遍（run 合并 / done 收尾 / 换步兜底），
最后看剩下几个 running。这才是用户能看到的东西。
"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://10.201.31.10:8011"
PNG = ("iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAYAAADED76LAAAAHElEQVQoz2NkYPjPQAxg"
       "YhgFo2AUjIJRMApGwSgAAAsSAAGr0n0MAAAAAElFTkSuQmCC")
IMAGE = "data:image/png;base64," + PNG


class Steps:
    """照搬 frontend/js/ask.js 里 applyStatus 的步骤合并逻辑。"""

    def __init__(self):
        self.steps = []

    def feed(self, p):
        if not isinstance(p, dict):
            return
        stage = p.get("stage") or "step"
        state = p.get("state")
        last = self.steps[-1] if self.steps else None

        if state == "done":
            if last and last["stage"] == stage:
                last["state"] = "done"
            else:
                # 没见到对应的 run 也要记下来，前端就是这么做的
                self.steps.append({"stage": stage, "state": "done"})
            return

        # 同阶段的进度刷新：不新开一步
        if last and last["stage"] == stage and last["state"] == "running":
            return

        # 上一步还没 done 就开了新步：前端会兜底把它收掉
        if last and last["state"] == "running":
            last["state"] = "done"
        self.steps.append({"stage": stage, "state": "running"})

    def running(self):
        return [s["stage"] for s in self.steps if s["state"] == "running"]

    def plain(self):
        return "  ".join("%s=%s" % (s["stage"], s["state"]) for s in self.steps) or "（无步骤）"


def ask(query, image, report, label):
    payload = {"query": query, "history": [], "image": image, "report": report}
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    print("=" * 92)
    print("【%s】query=%r  image=%s  report=%r" % (label, query, "有" if image else "无", report))
    print("=" * 92)
    raw = 0
    st = Steps()
    route = None
    with urllib.request.urlopen(req, timeout=300) as r:
        ev = data = ""
        for line_b in r:
            line = line_b.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
            elif line == "" and ev:
                try:
                    p = json.loads(data)
                except Exception:                                  # noqa: BLE001
                    p = data
                if ev == "status":
                    raw += 1
                    st.feed(p)
                elif ev == "done":
                    route = p.get("route")
                elif ev == "error":
                    print("   ERROR  %s" % p)
                ev = data = ""
    print("   原始 status 事件 %d 个" % raw)
    print("   合并后的步骤：%s" % st.plain())
    print("   路由：%s" % route)
    run = st.running()
    if run:
        print("   ★ 结束后仍停在 running 的步骤：%s  —— 用户会看到一直转圈" % "、".join(run))
    else:
        print("   √ 全部已收尾，不会转圈")
    return run, route


print("#" * 92)
print("# 按前端步骤合并规则判定（这才是用户看到的东西）")
print("#" * 92)
bad = 0
cases = [
    ("这是什么", IMAGE, None, "发图+文字·普通"),
    ("这是什么", IMAGE, "photo", "发图+文字·研判"),
    ("", IMAGE, None, "只发图·普通"),
    ("111", None, None, "纯文字"),
    ("你好", None, None, "纯文字·问候"),
]
for q, im, rep, label in cases:
    run, _ = ask(q, im, rep, label)
    bad += len(run)
    print()

print("=" * 92)
if bad:
    print("失败：共 %d 个步骤停在 running" % bad)
else:
    print("通过：五种路径结束后都没有停在 running 的步骤")
print("=" * 92)
