#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成「20 条好题型线上实跑」完整报告。

输入：
  _工作记录/实跑20条_输出v2.jsonl      实跑（含引用正文与元数据）
  _工作记录/实跑20条_评分v2.jsonl      judge 五维
  _工作记录/实跑20条_客观核验.md        数字可出处等客观指标（脚本生成）
输出：
  _工作记录/2026-09-21-20条好题型线上实跑.md
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
D = WS / "_工作记录"
OUT = D / "2026-09-21-20条好题型线上实跑.md"

runs = {r["序号"]: r for r in
        (json.loads(l) for l in (D / "实跑20条_输出v2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
scs = {r["序号"]: r for r in
       (json.loads(l) for l in (D / "实跑20条_评分v2.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}
# v1 = 真跑（47s 平均）；v2 = 命中站点缓存（0s）。耗时取 v1 的真实生成用时。
v1 = {}
if (D / "实跑20条_输出.jsonl").is_file():
    v1 = {r["序号"]: r for r in
          (json.loads(l) for l in (D / "实跑20条_输出.jsonl").read_text(encoding="utf-8").splitlines() if l.strip())}

NUM = re.compile(r"\d+(?:\.\d+)?")


def nums(t: str) -> Counter:
    c: Counter = Counter()
    for m in NUM.finditer(t or ""):
        s = m.group(0)
        if len(s.replace(".", "")) >= 2:
            c[s.rstrip("0").rstrip(".") if "." in s else s] += 1
    return c


rows = []
for no in sorted(runs):
    r, s = runs[no], scs.get(no, {})
    q = r["题目"]
    src = " ".join((x.get("text") or "") for x in (r.get("引用") or []))
    a, h = nums(r["答案"]), nums(q + " " + src)
    miss = sum(v for k, v in a.items() if k not in h)
    rows.append({
        "no": no, "题型": r["题型"], "语言": r.get("语言"),
        "耗时": (v1.get(no) or {}).get("耗时s") or r["耗时s"],
        "缓存": (r["耗时s"] or 0) < 2,
        "字数": r["答案字数"], "引用": r["引用条数"],
        "依据": r["依据类条数"], "案例": r["案例类条数"],
        "rr": r.get("rerank_top1"), "dup": r.get("标题重复数"),
        "n": sum(a.values()), "miss": miss,
        "正确": s.get("correctness"), "覆盖": s.get("coverage"), "可操作": s.get("actionability"),
        "有据": s.get("grounding"), "边界": s.get("boundary"), "均分": s.get("均分"),
        "编造": len(s.get("fabrications") or []), "gap": s.get("data_gap"),
        "能答": s.get("answerable"), "brief": s.get("brief") or "",
    })

sc = [r for r in rows if isinstance(r["均分"], (int, float))]
dims = [("正确", "correctness"), ("覆盖", "coverage"), ("可操作", "actionability"),
        ("有据", "grounding"), ("边界", "boundary")]

L = ["# 20 条垃圾焚烧「好题型」线上实跑结果（2026-09-21）", "",
     "**一句话**：20 条全部答出、平均 47 秒、平均 7.2 条引用；judge 均分 **3.93/5**"
     "（正确 4.10、覆盖 4.65、可操作 3.40、有据 3.70、边界 3.80）。"
     "**答案里的数字 95.8% 能在题干或引用正文里找到**（比纯模型的 v5 时代强很多）；"
     "但 judge 认为 **16/20 条「引用资料不足以支撑题目所需」**、12 条有编造指控 —— "
     "说明**瓶颈在语料与检索，不在生成**。", "",
     "## 一、口径", "",
     "| 项 | 值 |", "|---|---|",
     "- 被测对象 | `http://10.201.31.10:8011/hybrid_search`（线上站点，RAG 路线，模型 `xishu-qingyu-v5`）",
     "- 题源 | `_工作记录/垃圾焚烧好题型20条.jsonl`（题型取自训练集/ v5 测试判分最好的几类）",
     "- 裁判 | `deepseek-v4-flash-guan`，五维 1–5 分，**把引用正文一起给它看**（否则无法判「有据」）",
     "- 客观核验 | 数字可出处（题面+引用正文）、rerank 分、引用构成、引用标准是否现行",
     "", f"## 二、总评分（{len(sc)} 条有分）", "",
     "| 维度 | 线上 RAG | v5 纯模型焚烧测试（对照） |", "|---|---|---|",
     f"| 正确性 | **{sum(r['正确'] for r in sc)/len(sc):.2f}** | 4.0 |",
     f"| 覆盖 | **{sum(r['覆盖'] for r in sc)/len(sc):.2f}** | 3.8 |",
     f"| 可操作 | **{sum(r['可操作'] for r in sc)/len(sc):.2f}** | 3.5 |",
     f"| 有据 | **{sum(r['有据'] for r in sc)/len(sc):.2f}** | —（纯模型无检索） |",
     f"| 边界（不编造） | **{sum(r['边界'] for r in sc)/len(sc):.2f}** | 3.9 |",
     f"| **均分** | **{sum(r['均分'] for r in sc)/len(sc):.2f}** | 3.5（满分口径换算不同） |", "",
     f"- 有编造指控：**{sum(1 for r in sc if r['编造'])}/20** 条（合计 {sum(r['编造'] for r in sc)} 处）",
     f"- 回答**主动说明「资料未提供」**：**{sum(1 for r in sc if r['gap'])}/20** 条（这是边界好的表现）",
     f"- judge 认为「引用里拿不到题目所需信息」：**{sum(1 for r in sc if r['能答'] is False)}/20** 条",
     f"- 客观核验：答案数字 {sum(r['n'] for r in rows)} 个，"
     f"**无出处 {sum(r['miss'] for r in rows)} 个（{sum(r['miss'] for r in rows)/max(1,sum(r['n'] for r in rows))*100:.1f}%）**", "",
     "> 注：耗时列取的是**首次真跑**的生成用时（平均 47s）。第二次复跑 20 条全部 0–1 秒返回、"
     "答案与首次逐字相同 —— 那是命中了站点 FAQ 缓存（见第七节），不是「又快又稳」。", "",
     "## 三、逐条结果", "",
     "| # | 题型 | 语言 | 耗时 | 字数 | 引用(依据/案例) | rerank | 数字(无出处) | 正确 | 覆盖 | 可操作 | 有据 | 边界 | 均分 |",
     "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
for r in rows:
    rrt = f"{r['rr']:.3f}" if isinstance(r["rr"], (int, float)) else "—"
    L.append(f"| {r['no']} | {r['题型']} | {r['语言']} | {r['耗时']:.0f}s | {r['字数']} | "
             f"{r['引用']}({r['依据']}/{r['案例']}) | {rrt} | {r['n']}({r['miss']}) | "
             f"{r['正确']} | {r['覆盖']} | {r['可操作']} | {r['有据']} | {r['边界']} | **{r['均分']}** |")

L += ["", "## 四、按题型看（线上实跑 vs 训练集判分）", "",
      "| 题型 | 条数 | 线上均分 | 训练集/v5 证据 | 线上表现一句话 |", "|---|---|---|---|---|"]
EV = {
    "专利创新与对比": "v5 测试 4/5",
    "趋势与差距分析": "v5 测试 5/5（最好）",
    "标准/政策解读": "v5 测试 5/5",
    "结构化撰写（方案/培训/框架）": "v5 测试 3/5",
    "合规审查（法规依据直答）": "黄金样本五维满分",
    "标准适用性判断": "专业案例 19/25",
    "技术摘要与提炼": "同类 22.1/25",
    "现场运行与故障诊断": "wte_en/field 均分 23.5/25（英文）",
}
for t, v in sorted({r["题型"] for r in rows} and
                   {t: [x for x in rows if x["题型"] == t] for t in {r["题型"] for r in rows}}.items(),
                   key=lambda kv: -(sum(x["均分"] for x in kv[1] if x["均分"]) / max(1, len([x for x in kv[1] if x["均分"]])))):
    vv = [x["均分"] for x in v if isinstance(x["均分"], (int, float))]
    avg = f"{sum(vv)/len(vv):.2f}" if vv else "—"
    note = "；".join(x["brief"][:30] for x in v[:2])[:90]
    L.append(f"| {t} | {len(v)} | **{avg}** | {EV.get(t,'—')} | {note} |")

# 客观核验摘要（引用 rerank / 重复 / 现行性）
rrs = [r["rr"] for r in rows if isinstance(r["rr"], (int, float))]
dts = Counter()
for no, r in runs.items():
    dts.update(r.get("doc_type分布") or {})
L += ["", "## 五、检索侧客观指标", "",
      f"- rerank 最高分：平均 **{sum(rrs)/len(rrs):.3f}**；最低三条 "
      + "、".join(f"#{r['no']}={r['rr']:.3f}" for r in sorted(rows, key=lambda x: x["rr"] or 0)[:3])
      + "（英文题几乎检索不到东西）",
      f"- 引用文档类型：{dict(dts)}。其中 `?` = **知识图谱概念节点**（不是文档）："
      "Pollutant 22、TreatmentTech 7、PollutionSource 5、Organization 3、Industry 2、Document 2、Law 1、Violation 1"
      f"，合计 {dts.get('?', 0)} 条、**占全部引用 {dts.get('?', 0)/sum(dts.values())*100:.0f}%**；"
      "它们的标题是裸概念词（「重金属」「生活垃圾」「利用」「锅炉」），**没有正文页可看**",
      f"- **同一文档被重复引用 {sum(r['dup'] for r in rows)} 处**（最多一条题重复 3 次）",
      "- 引用到的标准里 **2 条已废止**（#10 引到《三轮汽车和低速货车用柴油机排气污染物排放限值及测量方法》"
      "《研究堆运行安全规定》，与题目 `HG/T 3650-2012` 无关）",
      "", "## 六、语料侧根因（这次查出来的硬伤）", "",
      "| 问题 | 数据 | 影响 |", "|---|---|---|",
      "| **GB 18485-2014《生活垃圾焚烧污染控制标准》本体不在语料** | 提到它的块 529 个，"
      "**标题是它本人的 0 个**；其中 495 个来自环评报告的转述表格 | 焚烧最核心的排放限值只能从"
      "二手转述拿；#17/#19/#20 点名该标准，引用一条都没命中 |",
      "| 报告类块标题无辨识度 | **103,774 块（占环评报告块的 47.3%）**："
      "「环境影响报告书」93,787、「一、建设项目基本情况」6,574、"
      "「进行环境影响评价并公示环境影响报告书。本环境影响报告书第三章部分监测数据、第」1,764 | "
      "引用条目对用户没有辨识度，看不出是哪份报告 |",
      "| 索引里仍有已废止文本 | **2,519 块 status=已废止** | 有引到作废标准的风险（本轮已发生 2 次） |",
      "| 空标题块 | 1,495 块（0.56%） | 引用条目标题为空 |",
      "| 表格数值缺失（既有结论） | 2,110/3,452 份文档含 `![](images/*.jpg)` 表格占位（61%） | "
      "限值表在纯文本里丢了，靠报告转述文本兜底 |", "",
      "## 七、这次实跑暴露的运维问题", "",
      "1. **站点有 FAQ 响应缓存**：`FAQ_CACHE`（`/cache/stats`：size 49、maxsize 300、TTL 1800s、"
      "命中率 0.411）。同一问题第二次问 **0 秒返回完全相同的答案** —— 复测时必须先确认是真跑"
      "（响应里 `latency_s>0`），别把缓存命中当成「效果稳定」。这与之前审核侧踩过的缓存坑是同一类。",
      "2. **英文题在中文语料上基本检索不到**：#19 rerank 最高才 **0.082**、#20 **0.398**，"
      "答案却写到 10,589 / 6,087 字（其余题只 700–1,650 字）——检索无内容时模型自行长篇发挥。",
      "3. **答案被题目「喂饱」**：16/20 条 judge 判定引用不足以支撑题目所需，但答案看着完整，"
      "因为题面自带限值/条款 —— 上线后遇到「题面没给全」的真实提问，能力会明显低于本测试。", "",
      "## 八、建议（按性价比）", "",
      "1. **补 GB 18485-2014（及 GB 18484-2020）标准本体入语料** —— 一次补全，焚烧类限值问答的"
      "有据性立刻改观（这是本项目最核心的标准，现在只有二手转述）。",
      "2. **修报告类标题**（103,774 块）：标题取自正文首行，应改为「项目名 + 报告类型」，"
      "引用条目才有辨识度；顺带清理空标题 1,495 块。",
      "3. **把已废止的 2,519 块降权或标注**，避免引用作废标准（本轮已发生 2 次）。",
      "4. **英文提问要单独评估**：要么补英文语料，要么在检索不到时明确提示「未检索到相关资料」，"
      "而不是让模型自由发挥上万字。",
      "5. 复测纪律：**先看 `/cache/stats` 或响应 `latency_s`**，确认不是缓存命中。",
      "6. **知识图谱节点占引用 30%**：这些条目只有概念名、没有原文页，建议在前端与「查看原文」逻辑里"
      "区分标注（文档引用 vs 图谱关联），否则用户点进去是空的。", "",
      "---", "",
      "产物：`实跑20条_输出v2.jsonl`（含引用正文与元数据）、`实跑20条_评分v2.jsonl`（五维判分）、"
      "`实跑20条_客观核验.md`（数字可出处/检索指标）、"
      "脚本：`验20条_线上实跑v2.py`、`评20条v2.py`、`核验20条客观指标.py`、`写20条报告v2.py`；"
      "语料侧：`盘点语料元数据修正版.py`、`查焚烧标准块来源.py`"]

OUT.write_text("\n".join(L), encoding="utf-8")
print(f"→ {OUT.relative_to(WS)}（{len(L)} 行）")
