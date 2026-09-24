#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判定 bug 1 是不是"间歇性"的。

单次测试恰好没复现，但那说明不了问题 —— 照片研判报告有两三千字，
作为上一轮的助手消息会主导上下文，模型答什么取决于采样。
所以要**重复多次**统计比例，而不是跑一次就下结论。

同时对比三种历史形态，定位到底是哪一部分把话题粘住了：
  A. 带完整照片报告的历史（用户真实情况）
  B. 只带用户那一轮（空 content），不带助手报告
  C. 完全不带历史
"""
from __future__ import annotations

import json
import urllib.request

BASE = "http://10.201.31.10:8011"
PIC = ("图片", "照片", "图像", "拍摄", "画面", "影像", "图中", "该图", "照片中", "本图")

REPORT = """【一、图片类型】
其他现场

【二、图中可见事实】
1. 照片显示一个室内空间，地面为灰色水泥地，有少量杂物和灰尘。
2. 左侧有一个金属框架结构，类似货架或设备支架，上面放置了一些物品。
3. 右侧有一个白色的门或隔断，门上有把手。
4. 背景中可见一些管道或线缆沿墙壁和天花板布置。
5. 整体环境较为简陋，未见明显的固废贮存设施或标识。
6. 照片中没有人员活动，也没有明显的危险废物或一般固废堆放痕迹。

【三、核验清单】
| 检查项 | 图中可见情况 | 判定 | 依据 |
| --- | --- | --- | --- |
| 贮存分区 | 照片中未见明确的贮存分区 | 不适用 | — |
| 标识标志 | 图中未见危险废物识别标志 | 存疑 | — |
| 防渗防漏 | 地面为水泥地，未见防渗层 | 存疑 | — |

【四、研判结论】
该照片为普通室内场景，未发现明显的危险废物贮存违法行为。"""


def ask(query: str, history: list) -> str:
    payload = {"query": query, "history": history, "image": None, "report": None}
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    out = []
    with urllib.request.urlopen(req, timeout=300) as r:
        ev = data = ""
        for raw in r:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event:"):
                ev = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
            elif line == "" and ev:
                if ev == "chunk":
                    try:
                        out.append(json.loads(data))
                    except Exception:                              # noqa: BLE001
                        pass
                ev = data = ""
    return "".join(out)


CASES = {
    "A 带完整照片报告": [{"role": "user", "content": ""},
                        {"role": "assistant", "content": REPORT}],
    "B 只带用户空消息": [{"role": "user", "content": ""}],
    "C 不带历史": [],
}
N = 5

print("=" * 92)
print("每种历史形态问 5 次「111」，统计回答里提到图片的次数")
print("=" * 92)
summary = {}
for name, hist in CASES.items():
    hits = 0
    print()
    print("── %s ──" % name)
    for i in range(N):
        try:
            body = ask("111", hist)
        except Exception as e:                                     # noqa: BLE001
            print("   第 %d 次 请求失败：%s" % (i + 1, e))
            continue
        words = sorted({w for w in PIC if w in body[:600]})
        pic = bool(words)
        hits += pic
        print("   第 %d 次 %s  %s" % (i + 1, "[讲图片]" if pic else "[没讲图]",
                                      body[:60].replace("\n", " ")))
        if words:
            print("        命中词：%s" % "、".join(words))
    summary[name] = hits
    print("   → %d / %d 次在讲图片" % (hits, N))

print()
print("=" * 92)
print("判定")
print("=" * 92)
for k, v in summary.items():
    print("  %-18s %d/%d" % (k, v, N))
if summary.get("A 带完整照片报告", 0) > summary.get("C 不带历史", 0):
    print()
    print("  → 带上照片报告的历史会显著把话题粘在图片上 = **bug 1 根因确认**")
    print("     对策方向：照片研判那一轮的助手消息不应原样回灌为历史")
elif summary.get("A 带完整照片报告", 0) == 0:
    print()
    print("  → 本次仍未复现。需要用户提供更具体的复现步骤（是否带文字、间隔多久、是否同一张图）。")
