#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""细化占位方案：既要掰回话题，又不能诱发编造。

上一轮结论：历史里只要留着图片报告的实质内容，话题就被粘住（丙、丁都 4/4）。
"整段换成占位"是唯一有效的（1/4），但那个占位太含糊 —— 模型开始**编造**
别的研判报告（"某工地扬尘污染""某次噪声报警不属实"），这比原 bug 更糟。

所以这一轮比较两种更明确的占位，并额外测两件事：
  ① 编造率：回答里是否出现历史中根本不存在的事实（编造的报告、时间、地点）
  ② 会不会误伤正常追问：问"这个报告第二条是什么意思"时还能不能答

顺带验证：末轮 user 消息要不要写「（图片）」而不是空串。
"""
from __future__ import annotations

import json
import re
import urllib.request

BASE = "http://10.201.31.10:8011"
PIC = ("图片", "照片", "图像", "拍摄", "画面", "影像", "图中", "该图", "本图")

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
| 识别标志 | 图中未见危险废物识别标志 | 存疑 | — |

【四、研判结论】
该照片为普通室内场景，未发现明显的危险废物贮存违法行为。"""

# 图片识别首行（read_image 产出的检索用问题），前端 am.vision 里有这一段
VISION_LINE = "这张现场照片里是什么场所，是否存在固废贮存不规范的情况？"

PH_VAGUE = "（已针对用户上一轮上传的图片给出完整研判报告，正文从略。）"

PH_CLEAR = ("（上一轮：用户上传了一张图片，系统按现场照片研判流程给出了报告。"
            "该报告正文不在此处重复；若用户这轮的问题与那份报告无关，"
            "请只回答用户这一轮的问题，不要复述或推测报告内容。）")

PH_WITH_SUBJECT = ("（上一轮：用户上传了一张图片，图片识别结果是「%s」，"
                   "系统已据此给出研判报告（正文不在此处重复）。"
                   "请只回答用户这一轮提出的问题；若本轮问题与那张图片无关，"
                   "不要围绕图片作答，也不要猜测报告内容。）" % VISION_LINE)

# 编造特征：历史里根本没有的时间、地点、事件
FABRIC = ("扬尘", "噪声", "迁安", "唐山", "工地", "停产", "虚假标记", "报警",
          "2025-", "2024-", "2023-")


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
    "笼统占位": [USER_TURN, {"role": "assistant", "content": PH_VAGUE}],
    "明确占位": [USER_TURN, {"role": "assistant", "content": PH_CLEAR}],
    "明确占位+图片主题": [USER_TURN, {"role": "assistant", "content": PH_WITH_SUBJECT}],
}
N = 5

print("=" * 92)
print("测试一：问「111」—— 是否还在讲图片 / 是否编造别的事实（每种 5 次）")
print("=" * 92)
stats = {}
for name, hist in CASES.items():
    pic = fab = 0
    print()
    print("── %s ──" % name)
    for i in range(N):
        try:
            body = ask("111", hist)
        except Exception as e:                                     # noqa: BLE001
            print("   第 %d 次 失败：%s" % (i + 1, e))
            continue
        head = body[:600]
        w = sorted({x for x in PIC if x in head})
        f = sorted({x for x in FABRIC if x in head})
        pic += bool(w)
        fab += bool(f)
        tag = ("[讲图片]" if w else "[没讲图]") + (" [编造!]" if f else "")
        print("   第 %d 次 %-18s %s" % (i + 1, tag, body[:52].replace("\n", " ")))
        if f:
            print("        编造特征词：%s" % "、".join(f))
    stats[name] = (pic, fab)
    print("   → 讲图片 %d/%d　编造 %d/%d" % (pic, N, fab, N))

print()
print("=" * 92)
print("测试二：正常追问会不会被误伤 ——「这份报告的第二条是什么意思？」")
print("=" * 92)
for name, hist in CASES.items():
    h = hist + [{"role": "user", "content": "111"},
                {"role": "assistant", "content": "您好，请输入具体问题。"}]
    try:
        body = ask("这份报告的第二条是什么意思？", h)
    except Exception as e:                                         # noqa: BLE001
        print("  %-18s 失败：%s" % (name, e))
        continue
    knows = ("金属框架" in body) or ("货架" in body) or ("水泥" in body)
    print("  %-18s %s　%s" % (name, "[答得上报告细节]" if knows else "[答不上报告细节]",
                              body[:70].replace("\n", " ")))

print()
print("=" * 92)
print("汇总")
print("=" * 92)
for k, (p, f) in stats.items():
    print("  %-18s 讲图片 %d/%d　编造 %d/%d" % (k, p, N, f, N))
best = [k for k, (p, f) in stats.items() if p <= 1 and f == 0]
print()
if best:
    print("  → 推荐：%s（既掰回话题又不编造）" % "、".join(best))
else:
    print("  → 仍需权衡，见上表取舍")
