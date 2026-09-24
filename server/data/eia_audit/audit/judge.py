#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""④ 判定与表述层：把「判据结论 + 事实」合成审核意见。

硬约束（方案里最重要的一条机械边界）：
  · **结论由代码根据判据 JSON 算出**，模型只负责写理由文字，不得改结论、不得加证据。
  · 四态：存在问题 / 存在疑似问题 / 优化调整建议 / 无问题。
    缺事实**一律**是「存在疑似问题」，绝不允许写成「存在问题」（本项目吃过这个亏）。
  · 每条意见必须带：判据出处（文件+条款/表号）、事实页码、可回溯原文。
  · 报告书类项目不设"专项评价"，相应审核项标记**不适用**，而不是硬判"无问题"。
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit.criteria import Fact, Criteria  # noqa: E402
from audit.extract import map_to_catalog_terms  # noqa: E402
# 共享原语（四态/数据结构/判据出处）在 model.py，避免 5-18 项那边反向导入造成循环
from audit.model import (CATALOG, GUIDE, SEVERITY, S_NA, S_OK,  # noqa: E402,F401
                         S_PROBLEM, S_SUGGEST, S_SUSPECT, TIER_ORDER,
                         Evidence, Item)
# 审核项 5-18（专项评价全要素 + 环境风险 + 报告质量）在 items_extra 里，
# 放同一层是为了让 judge.py 保持"总入口 + 前 4 项"的可读规模。
from audit.items_extra import (SPECIAL_ELEMENTS, judge_completeness,  # noqa: E402
                               judge_conclusion, judge_risk_identification,
                               judge_risk_potential, judge_risk_q_calc,
                               judge_risk_threshold, judge_special_element,
                               judge_special_quota, judge_standard_citations,
                               judge_targets_table)

# ---------------------------------------------------------------- 输入合并
def merge_inputs(regex_in: dict, llm_in: dict) -> tuple:
    """合并正则与模型两路判据输入。**两路冲突时留给人工，不擅自取一个。**

    为什么两路都要：正则快但会假阳性（实测"未直接排入"被当成直排），
    模型准但会编（实测编出"海水淡化装置"）。两路一致才敢直接用；
    不一致时按"模型已通过原文核验"取模型值，但把冲突记进需人工确认。
    """
    merged, conflicts, notes = {}, [], []
    for k in set(list(regex_in.keys()) + list(llm_in.keys())):
        r = regex_in.get(k)
        l = llm_in.get(k)
        rv = r.get("value") if isinstance(r, dict) else None
        lv = l.get("value") if isinstance(l, dict) else None
        l_ok = bool(isinstance(l, dict) and l.get("verified"))
        if rv is not None and lv is not None and rv != lv:
            conflicts.append({"输入": k, "正则": rv, "模型": lv,
                              "模型依据": l.get("quote", "")[:80],
                              "模型页码": l.get("page"),
                              "正则依据": (r or {}).get("quote", "")[:80],
                              "正则页码": (r or {}).get("page")})
            merged[k] = lv if l_ok else None
            notes.append(f"{k}：正则与模型结论相反，已暂按模型（带原文核验）取值，需人工确认")
        elif l_ok:
            merged[k] = lv
        elif rv is not None:
            merged[k] = rv
        elif lv is not None:
            merged[k] = lv          # 模型未过核验但正则也没有 → 仍取回填，后面会被标低置信
        else:
            merged[k] = None
    return merged, conflicts, notes


def provenance(k: str, regex_in: dict, llm_in: dict) -> dict:
    for src, d in (("llm", llm_in.get(k)), ("table/regex", regex_in.get(k))):
        if isinstance(d, dict) and d.get("value") is not None:
            return {"来源": d.get("method") or src, "页码": d.get("page"),
                    "原文": d.get("quote", ""), "核验": bool(d.get("verified", True)),
                    "说明": d.get("note") or d.get("_reject") or ""}
    return {}


# ---------------------------------------------------------------- 反向事实
NEG_RX = r"(不|未|无|没有|不属于|不涉及|不采用|不使用|不含|不在)"


def negation_facts(rep, item: dict, limit: int = 1) -> list:
    """为名录条目里的**定性**条件找"报告明确不涉及"的依据（否定事实）。

    没有这个能力，判据层就无法排除报告书档，只能永远答"不确定"。
    做法保守：只在原文出现「否定词 + 条件原话」或「条件原话 + 否定词」时才认，
    不认改写（改写交给人工），避免自己造出假的反向事实。
    """
    out = []
    for tier in ("报告书", "报告表"):
        for c in item["_cond"].get(tier, []):
            if c.kind != "qualitative" or c.raw.strip().startswith("其他"):
                continue
            core = c.raw.rstrip("的").strip()
            if len(core) < 3:
                continue
            for rx in (NEG_RX + r"[^。\n]{0,12}" + re.escape(core),
                       re.escape(core) + r"[^。\n]{0,8}" + NEG_RX):
                hits = rep.search(rx, max_hits=limit, ctx=60)
                if hits:
                    h = hits[0]
                    out.append(Fact(name=core, present=False, category=c.raw,
                                    page=h["page"], quote=h["snippet"],
                                    extra={"依据": f"原文否定式命中：{rx[:28]}…"}))
                    break
    return out


def build_query(ex) -> str:
    """名录查询串：报告自述条目 + 行业类别 + 项目名称 + 物料名称。

    顺序与权重都重要：报告自述的条目/情形是最强信号（判据层给它最高分），
    所以必须排在前面。
    """
    def _v(k):
        f = ex.basic.get(k)
        return (f.value or "") if f else ""
    return " ".join(filter(None, [
        _v("名录条目"), _v("行业类别自述"), _v("国民经济行业"), _v("行业类别"), _v("项目名称"),
        " ".join(m["名称"] for m in ex.materials[:40]),
    ]))


def pick_item(ex, C: Criteria, top: int = 5):
    q = build_query(ex)
    items = C.find_items(q, top=top)
    return items[0] if items else None


# ---------------------------------------------------------------- 审核项 1
def judge_category(rep, ex, C: Criteria, cond_facts: list = None, verbose: bool = False) -> Item:
    """环评类别准确性：报告实际类型 vs 名录应编类型。"""
    it = Item(审核项="环评类别准确性", 类别="法规符合性")
    kind_f = ex.basic.get("环评文件类型")
    actual = kind_f.value if kind_f else None
    if not actual:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "未能从报告中确定其环评文件类型（报告书/报告表），无法与名录比对。"
        it.需人工确认.append("报告类型未识别")
        return it

    # 查询串：报告自述的名录条目 + 行业类别 + 项目名称 + 物料名称
    # 顺序与权重都重要：报告自述的条目/情形是最强信号（判据层会给它最高分）
    query = build_query(ex)
    items = C.find_items(query, top=5)
    if not items:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "未能把本项目对应到《分类管理名录》任何条目，无法判定应编类别。"
        it.需人工确认.append("名录条目未匹配")
        return it

    mp = map_to_catalog_terms(ex.materials)
    facts = []
    for cat, b in mp["buckets"].items():
        first = b["items"][0]
        facts.append(Fact(name=cat, value=b["total"], unit=b["unit"] or "吨",
                          category=cat, page=first["页码"], quote=first["原文"]))
    negs = negation_facts(rep, items[0]) if items else []
    facts += negs
    # 报告自述的名录情形是一条**肯定事实**：报告表 表一里就写着
    # 「十九、非金属矿物制品业52.玻璃及玻璃制品（其他玻璃制造）」，
    # 「其他玻璃制造」正是一条判据条件的原文 —— 用它就能把档位锁到报告表。
    ref = ex.basic.get("名录条目")
    if ref and ref.value and ref.page:
        facts.append(Fact(name="报告自述名录情形", category=str(ref.value),
                          page=ref.page, quote=ref.quote or str(ref.value)))
    # 未覆盖的定性条件：逐条问过模型的（带原文核验），转成肯定/否定事实
    for cf in (cond_facts or []):
        if cf.get("page"):
            facts.append(Fact(name=cf["raw"], present=bool(cf["present"]),
                              category=cf["raw"], page=cf["page"],
                              quote=cf.get("quote", ""),
                              extra={"tier": cf.get("tier")}))

    d = C.decide_env_category(items, facts)
    item = d["item"]
    it.判据轨迹 = {"名录序号": item["no"], "名录条目": item["category"],
                   "报告自述名录条目": (ex.basic.get("名录条目").value
                                        if ex.basic.get("名录条目") else None),
                   "报告书条件": item["report_book"], "报告表条件": item["report_form"],
                   "登记表条件": item["registry"],
                   "候选打分": getattr(C, "_last_scores", [])[:3],
                   "判定": {k: v for k, v in d.items()
                            if k in ("decided", "tier", "unknown", "preliminary",
                                     "residual", "exclusion_state", "caveat", "basis")},
                   "物料归属": {k: {"合计": v["total"], "单位": v["unit"],
                                    "依据": v["basis"],
                                    "明细": v["items"]} for k, v in mp["buckets"].items()},
                   "未归属物料": mp["unmapped"][:12],
                   "否定事实": [{"条件": f.category, "页码": f.page, "原文": f.quote}
                                for f in negs]}
    it.参考依据 = (f"{CATALOG} 序号{item['no']}「{item['category']}」："
                   f"报告书——{item['report_book'] or '无'}；"
                   f"报告表——{item['report_form'] or '无'}")
    it.证据 = [Evidence(f.page, f.quote, f"反向事实：{f.category}") for f in negs
               if f.citable][:3]
    if ref and ref.value and ref.page:
        it.证据.insert(0, Evidence(ref.page, ref.quote or str(ref.value), "报告自述名录情形"))
    if kind_f and kind_f.page:
        it.证据.insert(0, Evidence(kind_f.page, kind_f.quote, "报告类型"))
    for f in facts:
        if f.citable and f.present and f.value is not None:
            it.证据.insert(0, Evidence(f.page, f.quote, f"物料：{f.name}"))
    it.证据 = it.证据[:4]
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)

    if not d["decided"]:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"按名录序号{item['no']}，应编类别**无法确定**（{d['basis'].get('hit_detail', '')}）。"
                   f"报告实际按「{actual}」编制。缺事实不得判违规，需补充核实后再定。")
        it.需人工确认.append("名录条件所需事实不足")
        return it

    should = d["tier"]
    it.置信度 = "高" if not d.get("exclusion_state") == "unknown" else "中"
    cmp = TIER_ORDER.get(should, 0) - TIER_ORDER.get(actual, 0)
    if cmp > 0:
        it.AI审核 = S_PROBLEM
        it.理由 = (f"名录序号{item['no']}「{item['category']}」规定：{item['report_book'] or item['report_form']}；"
                   f"本项目触发条件为 {d['basis'].get('hit_detail', '')}，应编**{should}**，"
                   f"但报告按「{actual}」编制，**降低了环评文件等级**。")
    elif cmp == 0:
        it.AI审核 = S_OK
        it.理由 = (f"名录序号{item['no']}「{item['category']}」对应档为**{should}**，"
                   f"与报告实际编制的「{actual}」一致。")
    else:
        it.AI审核 = S_SUGGEST
        it.理由 = (f"名录序号{item['no']}对应档为{should}，报告按「{actual}」编制，"
                   f"评价深度高于名录要求，不构成违规，仅提示。")
    if d.get("caveat"):
        it.需人工确认.append(d["caveat"])
    return it


# ---------------------------------------------------------------- 审核项 2-4
SPECIAL_MAP = {"大气": "大气专项评价设置", "地表水": "地表水专项评价设置",
               "地下水": "地下水专项评价设置"}


def judge_special(rep, ex, C: Criteria, merged: dict, element: str,
                  prov: dict, applied_kind: str) -> Item:
    """专项评价设置完整性（污染影响类报告表）。"""
    it = Item(审核项=SPECIAL_MAP[element], 类别="技术导则符合性")
    if applied_kind != "报告表":
        it.适用 = False
        it.AI审核 = S_NA
        it.置信度 = "高"
        it.理由 = (f"本项仅针对《报告表编制技术指南（污染影响类）》适用对象；"
                   f"本报告为「{applied_kind}」，按相应导则体系开展各要素评价，"
                   f"不受表1专项评价设置规则约束，故**不适用**。")
        return it

    res = {r["element"]: r for r in C.eval_special_industrial(merged)}
    r = res.get(element)
    if not r:
        it.AI审核 = S_SUSPECT
        it.理由 = f"判据库未给出「{element}」专项评价的判定规则。"
        return it
    stated = (ex.special_stated.get(element) or {})
    stated_set = stated.get("set")
    it.判据轨迹 = {"判据结论": r, "报告自述": stated or "未找到报告自述的专项评价设置表",
                   "判据输入": {k: merged.get(k) for k in (
                       "废气污染物清单", "厂界外500米内是否有环境空气保护目标",
                       "废水是否直排", "是否槽罐车外送污水处理厂",
                       "是否涉及集中式饮用水水源或特殊地下水资源保护区",
                       "是否新增河道取水", "取水口下游500米内是否有重要水生生物三场一通道")}}
    it.参考依据 = f"{GUIDE}：{element}专项评价设置条件——{_guide_text(element)}"

    keymap = {"大气": ["厂界外500米内是否有环境空气保护目标", "废气污染物清单"],
              "地表水": ["废水是否直排"], "地下水": ["是否涉及集中式饮用水水源或特殊地下水资源保护区"]}
    for k in keymap.get(element, []):
        p = prov.get(k)
        if p and p.get("页码"):
            it.证据.append(Evidence(p["页码"], p["原文"], f"{k}（来源 {p['来源']}）"))
    if not it.证据 and r.get("status") == "unknown":
        it.需人工确认.append(f"{element}专项评价所需的项目事实未抽取到")

    want = bool(r.get("set_special"))
    if r.get("status") == "unknown":
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"判据：{_guide_text(element)}。报告事实不足（{r.get('reason')}），"
                   f"无法判定是否应设{element}专项评价，需补充核实。")
    elif want and stated_set is False:
        it.AI审核 = S_PROBLEM
        it.置信度 = "高" if it.证据 else "中"
        it.理由 = (f"判据：{_guide_text(element)}。本项目符合设置条件（{r.get('reason')}），"
                   f"报告自述为**不设置**，缺少{element}专项评价内容。")
    elif want and stated_set is None:
        it.AI审核 = S_SUSPECT
        it.理由 = (f"判据：{_guide_text(element)}。本项目符合设置条件（{r.get('reason')}），"
                   f"但报告未明确自述专项评价设置情况，需人工确认是否已实际开展。")
    elif want:
        it.AI审核 = S_OK
        it.置信度 = "高" if it.证据 else "中"
        it.理由 = f"判据：{_guide_text(element)}。本项目符合设置条件，报告已设置该项专项评价。"
    elif stated_set is True:
        it.AI审核 = S_SUGGEST
        it.理由 = (f"判据：{_guide_text(element)}。本项目不符合设置条件（{r.get('reason')}），"
                   f"报告设置了该项专项评价，属从严，不构成违规，仅提示。")
    else:
        it.AI审核 = S_OK
        it.置信度 = "高" if it.证据 else "中"
        it.理由 = f"判据：{_guide_text(element)}。本项目不符合设置条件（{r.get('reason')}），报告未设置，符合要求。"
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    return it


def _guide_text(element: str) -> str:
    return {
        "大气": "排放废气中含有毒有害污染物、恶臭污染物，且厂界外500米范围内存在环境空气保护目标的建设项目，设置大气专项评价",
        "地表水": "新增排放工业废水直接排入环境的建设项目（槽罐车外送污水处理厂的除外），设置地表水专项评价",
        "地下水": "涉及集中式饮用水水源保护区，或热水、矿泉水、温泉等特殊地下水资源保护区的建设项目，设置地下水专项评价",
        "生态": "新增河道取水的污染类建设项目，取水口下游500米范围内有重要水生生物自然产卵场、索饵场、越冬场和洄游通道的，设置生态专项评价",
    }.get(element, "")


# ---------------------------------------------------------------- 总入口
def judge_report(rep, ex, C: Criteria, llm_in: dict = None, cond_facts: list = None,
                 verbose: bool = False) -> dict:
    llm_in = llm_in or {}
    regex_in = ex.special_inputs
    merged, conflicts, notes = merge_inputs(regex_in, llm_in)
    prov = {k: provenance(k, regex_in, llm_in) for k in merged}
    kind = (ex.basic.get("环评文件类型").value if ex.basic.get("环评文件类型") else None) or "未知"

    items = [judge_category(rep, ex, C, cond_facts=cond_facts, verbose=verbose)]
    for el in SPECIAL_ELEMENTS:
        items.append(judge_special_element(rep, ex, C, merged, el, prov, kind))
    items.append(judge_special_quota(ex, kind))
    items.append(judge_risk_identification(rep, ex, C))
    items.append(judge_risk_threshold(rep, ex, C))
    items.append(judge_risk_q_calc(rep, ex, C, merged))
    items.append(judge_risk_potential(rep, ex, C, kind))
    items.append(judge_targets_table(rep, ex))
    items.append(judge_completeness(rep, ex, kind))
    items.append(judge_standard_citations(rep, ex))
    items.append(judge_conclusion(rep, ex))

    return {
        "file": {
            "name": os.path.basename(rep.pdf),
            "sha1": rep.sha1,
            "pages": rep.pages,
            "环评文件类型": kind,
            "项目名称": (ex.basic.get("项目名称").value if ex.basic.get("项目名称") else None),
            "行业类别": (ex.basic.get("行业类别").value if ex.basic.get("行业类别") else None),
        },
        "items": [i.to_json() for i in items],
        # 判据输入按**键名排序**输出：merged 是两路输入合并的结果，字典顺序取决于
# 集合/遍历顺序，同一份报告两次跑会出现"结论完全一样、文件哈希不一样"。
# 审核结果要能当审计凭证，文件就该字节稳定（已实测过这个坑）。
        "判据输入": {k: {"值": merged[k], "来源": prov.get(k, {}).get("来源"),
                         "页码": prov.get(k, {}).get("页码"),
                         "原文": prov.get(k, {}).get("原文", "")[:160],
                         "核验": prov.get(k, {}).get("核验")}
                    for k in sorted(merged)},
        "冲突": conflicts,
        "说明": notes,
        "统计": {s: sum(1 for i in items if i.AI审核 == s)
                 for s in (S_PROBLEM, S_SUSPECT, S_SUGGEST, S_OK, S_NA)},
    }