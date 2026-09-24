#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对比几种修法，用数据选，不靠猜。

已确认：把上一轮的照片研判报告原样放进 history，问「111」时 5/5 次都在继续讲图片。
现在比较几种处理 history 的方式，看哪种真能把话题掰回来、又不丢对话连续性。

  甲 原样（现状，作为对照）
  乙 整段替换成一句占位
  丙 只留报告开头 200 字
  丁 留报告的一行摘要（首行"+ 结论段"拼的短摘要）
  戊 保留报告但**追加**一条系统级提示（模拟补 HISTORY_RULE）

每种跑 4 次，统计讲图片的比例。同时人眼看答案是否仍然连贯、可用。
"""
from __future__ import annotations

import json
import re
import urllib.request

BASE = "http://10.201.31.10:8011"
PIC = ("图片", "照片", "图像", "拍摄", "画面", "影像", "图中", "该图", "本图", "图所")

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
| 贮存分区（不相容废物分开） | 照片中未见明确的贮存分区 | 不适用 | — |
| 危险废物识别标志 | 图中未见危险废物识别标志 | 存疑 | — |
| 防渗防漏措施 | 地面为水泥地，未见防渗层 | 存疑 | — |

【四、研判结论】
该照片为普通室内场景，未发现明显的危险废物贮存违法行为。"""

PLACEHOLDER = "（已针对用户上一轮上传的图片给出完整研判报告，正文从略。）"


def summarize(text: str) -> str:
    """取"图片类型 + 研判结论"两段拼一句短摘要。"""
    kind = re.search(r"【一、图片类型】\s*\n(.+)", text)
    concl = re.search(r"【四、研判结论】\s*\n(.+)", text)
    parts = []
    if kind:
        parts.append("图片类型：%s" % kind.group(1).strip())
    if concl:
        parts.append("结论：%s" % concl.group(1).strip())
    return "（上一轮图片研判摘要）" + "；".join(parts) if parts else PLACEHOLDER


def ask(query: str, history: list) -> str:
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream",
        data=json.dumps({"query": query, "history": history, "image": None,
                         "report": None}, ensure_ascii=False).encode("utf-8"),
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


USER_TURN = {"role": "user", "content": "（图片）"}

CASES = {
    "甲 原样（现状）": [USER_TURN, {"role": "assistant", "content": REPORT}],
    "乙 整段换成占位": [USER_TURN, {"role": "assistant", "content": PLACEHOLDER}],
    "丙 只留开头 200 字": [USER_TURN, {"role": "assistant", "content": REPORT[:200] + "…"}],
    "丁 换成短摘要": [USER_TURN, {"role": "assistant", "content": summarize(REPORT)}],
}
N = 4

print("=" * 92)
print("问「111」，看回答是否还在讲图片（每种 4 次）")
print("=" * 92)
score = {}
samples = {}
for name, hist in CASES.items():
    hits = 0
    print()
    print("── %s ──" % name)
    for i in range(N):
        try:
            body = ask("111", hist)
        except Exception as e:                                     # noqa: BLE001
            print("   第 %d 次 失败：%s" % (i + 1, e))
            continue
        words = sorted({w for w in PIC if w in body[:600]})
        if words:
            hits += 1
        if i == 0:
            samples[name] = body[:150].replace("\n", " ")
        print("   第 %d 次 %s  %s" % (i + 1, "[讲图片]" if words else "[没讲图]",
                                      body[:56].replace("\n", " ")))
    score[name] = hits
    print("   → %d / %d" % (hits, N))

print()
print("=" * 92)
print("汇总")
print("=" * 92)
for k, v in score.items():
    bar = "█" * v + "·" * (N - v)
    print("  %-18s %d/%d  %s" % (k, v, N, bar))
print()
print("各方案第一次回答的开头（人眼判断是否仍然连贯可用）：")
for k, v in samples.items():
    print("  %-18s %s" % (k, v))
best = [k for k, v in score.items() if v == 0 and k != "甲 原样（现状）"]
print()
if best:
    print("  → 有效方案：%s" % "、".join(best))
else:
    print("  → 没有一种方案把话题完全掰回来，需要换思路（比如后端层面处理）")
