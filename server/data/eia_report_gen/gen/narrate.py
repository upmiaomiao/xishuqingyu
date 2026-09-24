# -*- coding: utf-8 -*-
"""叙述生成 + **出处闸门**（objective 的 ③：模型只写有出处约束的叙述）。

做法分两步，模型只参与第一步：

  ① 把填报数据与判定结果编成**事实表**（F1、F2…），每条事实都能追到"填报表的哪个字段"
     或"判据库的哪一条"；
  ② 模型按事实表写叙述，**每个含数字的句子必须在句末标注 [F#]**；
  ③ **代码闸门**逐句核验（这一步不许模型参与）：
     · 有数字却没标 [F#] → 剔除
     · 标的 [F#] 不存在 → 剔除
     · 句中的数字没在所引事实里出现 → 剔除（这就是"数字必须来自填报或判据库"）
     · 标准号（GB/HJ/DB…）一律不许出现在叙述里（标准清单另有候选表，须人工核定）
     被剔除的句子连同原因一起返回，写进生成说明里 —— 让人看得见"少写了什么、为什么"。

没有出处就不写，而不是写得像真的。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
AUDIT = os.environ.get("AUDIT_HOME") or os.path.join(WORK, "_脚本代码", "审核智能体")
if AUDIT not in sys.path:
    sys.path.insert(0, AUDIT)

PROMPT_VERSION = "narr-v2"      # C9（2026-09-23）：加了措施名出处闸门 → 旧缓存必须失效
CACHE_DIR = os.path.join(HERE, "_cache_narr")

SYSTEM = (
    "你是环评报告编写助手。**只能使用我给出的事实表**编写指定小节，不得引入任何外部知识、"
    "不得补充事实表里没有的数字、标准号、地名、企业名。\n"
    "硬性要求：\n"
    "1. 每个包含阿拉伯数字的句子，必须在句末标注它依据的事实编号，形如 [F3]；\n"
    "2. 一句话依据多条事实就都标上，如 [F2][F5]；\n"
    "3. 事实表里没有的内容，宁可不写（少写不算错，编造算错）；\n"
    "4. 不要出现任何标准号（GB/HJ/DB 等）；\n"
    "5. 只输出正文，不要标题、不要解释、不要 markdown 标记。"
)

STD_RX = re.compile(r"(?:GB|HJ|DB|GBZ|JGJ|CJJ)\s*/?\s*(?:T|Z)?\s*\d{2,5}")
NUM_RX = re.compile(r"\d+(?:\.\d+)?")
SENT_RX = re.compile(r"[^。；;\n]+[。；;\n]?")
REF_RX = re.compile(r"\[F(\d+)\]")

# C9-②（2026-09-23）：**治理措施/设施名**词表。出处闸门原先只在句子里**有数字**时才核对，
# 全是文字的措施句（"采用布袋除尘器+喷淋塔处理"）一个字都不核、原样放行 —— 用户看到的
# "开始编措施"就是这么来的。这里改成：出现这类词而**事实表里没有同名文本** → 剔除。
# 只列可枚举的常见治理设施（不含工艺设备），宁可少列也不要误杀。
MEASURE_WORDS = (
    "布袋除尘", "袋式除尘", "静电除尘", "旋风除尘", "湿式除尘", "喷淋塔", "洗涤塔", "吸收塔",
    "活性炭", "催化燃烧", "蓄热燃烧", "RTO", "RCO", "UV光解", "光氧催化", "等离子",
    "SCR", "SNCR", "脱硝", "脱硫", "MBR", "膜生物反应器", "纳滤", "反渗透", "超滤",
    "生化处理", "混凝沉淀", "气浮", "隔油", "中和", "消毒", "隔声", "消声", "减振",
    "防渗", "集气罩", "密闭收集", "在线监测",
)


def _num_norm(s: str) -> str:
    return s.replace(",", "")


def build_facts(data: dict, dec: dict) -> list:
    """填报数据 + 判定结果 → 事实表（每条带出处）。"""
    facts = []

    def add(text, src):
        facts.append({"id": "F%d" % (len(facts) + 1), "text": str(text), "来源": src})

    for k, label in [("项目名称", "项目名称"), ("建设地点", "建设地点"), ("地理坐标", "地理坐标"),
                     ("建设性质", "建设性质"), ("国民经济行业类别", "国民经济行业类别"),
                     ("建设项目行业类别", "建设项目行业类别")]:
        v = data.get(k)
        if v not in (None, "", []):
            add(f"{label}：{v}", f"填报表.{k}")
    for k, label, unit in [("用地面积_m2", "用地面积", "m²"), ("总投资_万元", "总投资", "万元"),
                           ("环保投资_万元", "环保投资", "万元")]:
        v = data.get(k)
        if isinstance(v, (int, float)):
            add(f"{label}：{v}{unit}", f"填报表.{k}")
    add("是否开工建设: " + ("是" if data.get("是否开工建设") else "否"), "填报表.是否开工建设")
    for k, label in [("工艺流程简述", "主要工艺流程"), ("水平衡说明", "水平衡分析"),
                     ("规划情况", "规划情况"), ("规划环评情况", "规划环境影响评价情况"),
                     ("区域环境质量现状", "区域环境质量现状"), ("总量控制指标", "总量控制指标")]:
        v = data.get(k)
        if v not in (None, "", []):
            add(f"{label}：{v}", f"填报表.{k}")
    for k, label, keys in [("产品及产能", "主要产品及产能", ("名称", "产能", "单位")),
                           ("主要原辅材料", "主要原辅材料", ("名称", "年用量", "单位")),
                           ("主要生产设备", "主要生产设施", ("名称", "数量", "规格")),
                           ("产排污环节", "产排污环节", ("环节", "污染物", "排放去向")),
                           ("环保措施", "环境保护措施", ("要素", "措施内容", "排放去向"))]:
        for it in (data.get(k) or []):
            if isinstance(it, dict) and any(it.get(x) not in (None, "") for x in keys):
                add(f"{label}：" + "，".join(f"{x}={it.get(x)}" for x in keys
                                            if it.get(x) not in (None, "")), f"填报表.{k}")
    for t in (data.get("补充事实") or []):
        if isinstance(t, dict) and t.get("名称"):
            if t.get("不适用") is True:
                add(f"{t['名称']}：本项目不适用该情形", "填报表.补充事实")
            elif t.get("值") is not None:
                add(f"{t['名称']}：{t['值']}{t.get('单位') or ''}", "填报表.补充事实")
    # 判定结果（来自判据库，带依据）
    c = dec.get("名录") or {}
    if c.get("名录条目"):
        add(f"名录条目：{c.get('名录条目')}（序号{c.get('名录序号')}）；"
            f"报告书条件：{c.get('报告书条件') or '无'}；报告表条件：{c.get('报告表条件') or '无'}",
            "判据库.分类管理名录")
    if c.get("decided"):
        add(f"应编制的环评文件类型：{c['tier']}", "判定层")
    for r in (dec.get("专项评价") or {}).get("要素", []):
        if r.get("set_special") is True:
            add(f"{r['element']}专项评价应设置，理由：{r['reason']}", "判据库.专项评价设置判据")
    return facts


def fact_sheet(facts: list) -> str:
    return "\n".join(f"[{f['id']}] {f['text']}" for f in facts)


def _cache_path(key: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    return os.path.join(CACHE_DIR, key + ".json")


def call_cached(section: str, instruction: str, facts: list, max_tokens: int = 700,
                fresh: bool = False) -> str:
    """按 (PROMPT_VERSION, 事实表, 小节) 缓存模型输出 —— 同一输入重复生成结果一致。

    fresh=True 是**用户主动要"重新生成"**：跳过读缓存、并把温度从 0 抬到 0.6，
    所以措辞会变；**而且不写缓存**，免得把确定性的那一份覆盖掉。
    代价：fresh 出来的稿子不再保证"同输入同字节"，这是刻意的取舍。
    """
    key = hashlib.sha1(json.dumps(
        {"v": PROMPT_VERSION, "s": section, "i": instruction,
         "f": [x["text"] for x in facts]}, ensure_ascii=False).encode("utf-8")).hexdigest()
    p = _cache_path(key)
    if not fresh and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)["text"]
    from audit.llm import call_model
    user = (f"事实表：\n{fact_sheet(facts)}\n\n"
            f"请编写小节「{section}」。要求：{instruction}\n"
            f"只写正文；含数字的句子必须标 [F#]。")
    text = call_model([{"role": "system", "content": SYSTEM},
                       {"role": "user", "content": user}],
                      max_tokens=max_tokens, temperature=(0.6 if fresh else 0.0))
    text = (text or "").strip()
    if not fresh:                       # 重新生成的那一版不进缓存，保住确定性基线
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"text": text, "key": key, "PROMPT_VERSION": PROMPT_VERSION,
                       "section": section}, f, ensure_ascii=False, indent=1)
    return text


def gate(text: str, facts: list) -> dict:
    """出处闸门：逐句核验，返回 {保留, 剔除:[{句, 原因}]}。"""
    by_id = {f["id"]: f["text"] for f in facts}
    kept, dropped = [], []
    for raw in SENT_RX.findall(text or ""):
        s = raw.strip()
        if not s:
            continue
        refs = REF_RX.findall(s)
        # 必须先去掉 [F#] 标签再抽数字：否则标签里的编号（[F23] → 23）会被当成
        # 正文数字去核对，结果**每一句都被判"数字无出处"**（实测踩过，正文全空）。
        body = REF_RX.sub("", s)
        nums = NUM_RX.findall(_num_norm(body))
        if STD_RX.search(body):
            dropped.append({"句": s, "原因": "叙述里出现标准号（标准清单另行给候选，须人工核定）"})
            continue
        # C9-②：措施名必须能在事实表里找到同名文本，否则就是模型按行业常识自己补的。
        # 放在"无数字句直接放行"**之前** —— 正是这类没有数字的句子原先一路畅通。
        hit_m = [w for w in MEASURE_WORDS
                 if w in body and not any(w in f["text"] for f in facts)]
        if hit_m:
            dropped.append({"句": s, "原因": "措施名无出处：%s（事实表里没有对应措施）"
                            % "、".join(hit_m[:4])})
            continue
        if not nums:
            kept.append(body.strip())
            continue
        if not refs:
            dropped.append({"句": s, "原因": "含数字但未标注出处 [F#]"})
            continue
        unknown = [r for r in refs if ("F" + r) not in by_id]
        if unknown:
            dropped.append({"句": s, "原因": "标注了不存在的事实编号 %s" % ",".join(unknown)})
            continue
        allowed = " ".join(_num_norm(by_id["F" + r]) for r in refs)
        bad = [n for n in nums if n not in allowed]
        if bad:
            dropped.append({"句": s, "原因": "数字 %s 不在所引事实（%s）中"
                            % ("、".join(bad), ",".join("F" + r for r in refs))})
            continue
        kept.append(body.strip())
    return {"保留": "".join(kept).strip(), "剔除": dropped}


# 只对"填报里有事实支撑"的小节调用模型；没有事实支撑的一律留给人工
SECTIONS = [
    ("工艺流程和产排污环节概述",
     "依据主要工艺流程、主要设施、产排污环节，写 2~4 句概述，说明工艺与产污的关系。"),
    ("运营期环境影响和保护措施概述",
     "依据环境保护措施与产排污环节，逐要素（废气/废水/噪声/固废等，按事实表里有的）写措施概述，"
     "1 个要素 1 句。**措施与设施名称必须逐字取自事实表**，事实表里没有的措施一律不要写。"),
    ("规划及规划环境影响评价符合性分析",
     "依据规划情况与规划环评情况写 1~2 句；若填报表写的是「无」，就照实说明本项目不涉及相关规划。"),
]


def _has_measure(data: dict) -> bool:
    """填报里**真的有**环境保护措施内容吗（而不是字段在、内容空）。

    2026-09-23 实测教训：`环保措施` 是**必填项**，用户不可能"整个字段不填"（接口会判 rejected）。
    真正会发生的是——字段在、里面是空行。所以判据必须看 `措施内容` 有没有字，
    不能只看字段在不在，也不能只看事实表里有没有"环境保护措施"这个前缀。
    """
    for r in (data.get("环保措施") or []):
        if isinstance(r, dict) and str(r.get("措施内容") or "").strip():
            return True
        if isinstance(r, str) and r.strip():
            return True
    return False


def narrate(data: dict, dec: dict, sections=None, fresh: bool = False) -> dict:
    facts = build_facts(data, dec)
    out = {"事实表": facts, "小节": {}, "PROMPT_VERSION": PROMPT_VERSION, "重新生成": bool(fresh)}
    # C9-①（2026-09-23）：填报里没有**实质**环保措施时，不生成"措施概述"小节 ——
    # 原先只是把指令发过去，模型就按行业常识自己补一整套措施（用户原话"开始编措施"）。
    # 少写不算错，编造算错：宁可不写这一节，留给人工。
    has_measure = _has_measure(data)
    for name, ins in (sections or SECTIONS):
        if (not has_measure) and ("保护措施概述" in name):
            out["小节"][name] = {"正文": "", "剔除": [], "模型原文": "",
                                 "跳过原因": "填报表未给「环境保护措施」事实，本小节不生成"
                                             "（事实表里没有措施可依，宁可不写）"}
            continue
        text = call_cached(name, ins, facts, fresh=fresh)
        g = gate(text, facts)
        out["小节"][name] = {"正文": g["保留"], "剔除": g["剔除"], "模型原文": text}
    return out


def main():
    import io
    if len(sys.argv) < 2:
        print("用法：python narrate.py 填报表.json")
        return 1
    base = os.path.dirname(HERE)
    sys.path.insert(0, base)
    from gen import decide, schema
    data = schema.load(sys.argv[1])
    dec = decide.decide(data)
    r = narrate(data, dec)
    print("事实表 %d 条" % len(r["事实表"]))
    for name, v in r["小节"].items():
        print("\n== %s" % name)
        print("  正文：", v["正文"][:300] or "（空）")
        for d in v["剔除"]:
            print("  ✗ 剔除：%s → %s" % (d["句"][:60], d["原因"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())