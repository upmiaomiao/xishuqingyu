#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""④ 判定层 · 审核项 5-18（在 judge.py 的 1-4 项之后接入）。

设计纪律（沿用 P2）：
  · 能机械算的由代码算：临界量比对、Q 值复算、矩阵查表、数量上限、必备章节是否存在；
  · 算不出来的**绝不编**：转「存在疑似问题」并写明缺哪条事实；
  · 每条结论都带：判据原文出处、页码、证据摘录、判据轨迹。
"""
from __future__ import annotations

import re

from audit.model import (GUIDE, S_NA, S_OK, S_PROBLEM, S_SUGGEST,  # noqa: E402
                         S_SUSPECT, Evidence, Item)

# 专项评价设置：表1 覆盖的要素（污染影响类）。土壤/声环境在表1 正文明确"不开展"。
SPECIAL_ELEMENTS = ("大气", "地表水", "地下水", "生态", "海洋", "环境风险", "土壤", "声环境")
SPECIAL_MAP = {
    "大气": "大气专项评价设置", "地表水": "地表水专项评价设置",
    "地下水": "地下水专项评价设置", "生态": "生态专项评价设置",
    "海洋": "海洋专项评价设置", "环境风险": "环境风险专项评价设置",
    "土壤": "土壤专项评价设置", "声环境": "声环境专项评价设置",
}
GUIDE_TEXT = {
    "大气": "排放废气中含有毒有害污染物、恶臭污染物，且厂界外500米范围内存在环境空气保护目标的建设项目，设置大气专项评价",
    "地表水": "新增排放工业废水直接排入环境的建设项目（槽罐车外送污水处理厂的除外），设置地表水专项评价",
    "地下水": "涉及集中式饮用水水源保护区，或热水、矿泉水、温泉等特殊地下水资源保护区的建设项目，设置地下水专项评价",
    "生态": "新增河道取水的污染类建设项目，取水口下游500米范围内有重要水生生物自然产卵场、索饵场、越冬场和洄游通道的，设置生态专项评价",
    "海洋": "直接向海排放污染物的海洋工程建设项目，设置海洋专项评价",
    "环境风险": "有毒有害和易燃易爆危险物质存储量超过临界量的建设项目，设置环境风险专项评价",
    "土壤": "表1 正文明确：土壤**不开展**专项评价",
    "声环境": "表1 正文明确：声环境**不开展**专项评价",
}
# 每个要素要看哪些判据输入（用于证据与轨迹）
INPUT_KEYS = {
    "大气": ["废气污染物清单", "厂界外500米内是否有环境空气保护目标"],
    "地表水": ["废水是否直排", "是否槽罐车外送污水处理厂", "是否为污水集中处理厂"],
    "地下水": ["是否涉及集中式饮用水水源或特殊地下水资源保护区"],
    "生态": ["是否新增河道取水", "取水口下游500米内是否有重要水生生物三场一通道"],
    "海洋": ["是否直接向海排放污染物的海洋工程"],
    "环境风险": ["危险物质清单"],
    "土壤": [], "声环境": [],
}
MARINE_RX = re.compile(r"海洋工程|直接向海排放|入海排污口|海域使用|填海")


def _ev(page, quote, source):
    return Evidence(page, quote, source)


# ---------------------------------------------------------------- 5-9：专项评价设置
def judge_special_element(rep, ex, C, merged: dict, element: str, prov: dict,
                          applied_kind: str) -> Item:
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

    it.判据轨迹 = {"判据结论": r,
                   "报告自述": (ex.special_stated.get(element) or "未找到报告自述的专项评价设置表"),
                   "判据输入": {k: merged.get(k) for k in INPUT_KEYS.get(element, [])}}
    it.参考依据 = f"{GUIDE}表1：{element}专项评价设置条件——{GUIDE_TEXT.get(element, '')}"

    for k in INPUT_KEYS.get(element, []):
        p = prov.get(k)
        if p and p.get("页码"):
            it.证据.append(_ev(p["页码"], p["原文"], f"{k}（来源 {p['来源']}）"))

    stated = ex.special_stated.get(element) or {}
    stated_set = stated.get("set")

    # 海洋：判"是不是海洋工程"要看**项目性质**（名称/行业类别），不能靠全文关键词 ——
# 报告常把表1 原文抄进"编制依据/专项评价设置"章节，关键词一抓一个准，反而判不出。
    if element == "海洋" and r.get("status") == "unknown":
        nm = str(getattr(ex.basic.get("项目名称"), "value", "") or "")
        ind = str(getattr(ex.basic.get("行业类别"), "value", "") or "")
        blob = nm + " " + ind
        if not re.search(r"海洋工程|港口|码头|围填海|航道|疏浚|跨海|海底", blob):
            r = {"element": "海洋", "set_special": False, "status": "decided",
                 "reason": f"按项目性质（名称「{nm or '未抽到'}」/行业类别「{ind or '未抽到'}」）"
                           f"不属于海洋工程，不直接向海排放污染物"}
            it.判据轨迹["判据结论"] = r
            src = ex.basic.get("项目名称") or ex.basic.get("行业类别")
            if src is not None and getattr(src, "page", None):
                it.证据.append(_ev(src.page, getattr(src, "quote", "") or src.value,
                                   "项目名称/行业类别（来源 basic）"))
            it.置信度 = "中" if it.证据 else "低"

    # 生态：报告全文没有"河道取水/取水口"表述的，就是"不新增河道取水"，
    # 不必因为模型没抽到"是否新增河道取水"就判疑似（锅炉/技改类项目常见）。
    if element == "生态" and r.get("status") == "unknown":
        if not rep.search(r"河道取水|取水口|取水工程|引水", max_hits=1, ctx=0):
            r = {"element": "生态", "set_special": False, "status": "decided",
                 "reason": "报告全文未见新增河道取水/取水口等表述，本项目不新增河道取水"}
            it.判据轨迹["判据结论"] = r
            it.置信度 = "低"

    if r.get("status") == "unknown":
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"判据：{GUIDE_TEXT.get(element, '')}。报告事实不足（{r.get('reason')}），"
                   f"无法判定是否应设{element}专项评价，需补充核实。")
        if not it.证据:
            it.需人工确认.append(f"{element}专项评价所需的项目事实未抽取到")
    elif r.get("set_special") and stated_set is False:
        it.AI审核 = S_PROBLEM
        it.置信度 = "高" if it.证据 else "中"
        it.理由 = (f"判据：{GUIDE_TEXT.get(element, '')}。本项目符合设置条件（{r.get('reason')}），"
                   f"报告自述为**不设置**，缺少{element}专项评价内容。")
    elif r.get("set_special") and stated_set is None:
        it.AI审核 = S_SUSPECT
        it.理由 = (f"判据：{GUIDE_TEXT.get(element, '')}。本项目符合设置条件（{r.get('reason')}），"
                   f"但报告未明确自述是否设置该项专项评价，需人工确认。")
    elif r.get("set_special"):
        it.AI审核 = S_OK
        it.置信度 = "高" if it.证据 else "中"
        it.理由 = f"判据：{GUIDE_TEXT.get(element, '')}。本项目符合设置条件，报告已设置该项专项评价。"
    elif stated_set is True:
        it.AI审核 = S_SUGGEST
        it.理由 = (f"判据：{GUIDE_TEXT.get(element, '')}。本项目不符合设置条件（{r.get('reason')}），"
                   f"报告设置了该项专项评价，属从严，不构成违规，仅提示。")
    else:
        it.AI审核 = S_OK
        it.置信度 = it.置信度 or ("高" if it.证据 else "中")
        it.理由 = (f"判据：{GUIDE_TEXT.get(element, '')}。本项目不符合设置条件"
                   f"（{r.get('reason')}），报告未设置，符合要求。")

    # 2026-09-22（用户反馈 A3）：废气污染物清单是从**关键词命中页**里抽的，
    # 而废水表里常见的「氨氮」会被裸的「氨」命中（已改成 氨(?!氮)），
    # 万一还是把废水内容抽进来了，就按用户要的"加一步人工核对"处理：
    #   强证据（该页出现废水标准号 GB8978/GB18918…）→ 直接挂"疑似抽串页，需人工核对"，
    #   弱证据（只出现 COD/氨氮/动植物油等水介质指标）→ 保留结论，但在理由里点一句。
    if element == "大气":
        _f = (getattr(ex, "special_inputs", None) or {}).get("废气污染物清单") or {}
        s_std = _f.get("suspect_std") or []
        s_water = _f.get("suspect_water") or []
        if s_std:
            pages = "、".join(f"第{p}页（{t}）" for p, t in s_std[:4])
            it.AI审核 = S_SUSPECT
            it.置信度 = "低"
            it.理由 = (it.理由 +
                       f"　⚠ 但**废气污染物清单疑似抽到废水内容**：{pages} 出现的是废水标准号，"
                       f"不是废气标准。该清单需人工核对后再采信（疑为跨页误抽）。")
            it.需人工确认.append("废气污染物清单疑似混入废水标准/水质指标，需人工核对页码")
            for p, t in s_std[:3]:
                it.证据.append(_ev(p, f"该页出现「{t}」（废水标准号）", "疑似串页：废水内容混入废气清单"))
        elif s_water:
            pages = "、".join(f"第{p}页（{t}）" for p, t in s_water[:3])
            it.理由 = (it.理由 +
                       f"　（提示：同一批页里 {pages} 出现水介质指标，若该页实为废水表，"
                       f"请人工核对废气清单是否被污染。）")
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    return it


# ---------------------------------------------------------------- 10：专项评价数量上限
def judge_special_quota(ex, applied_kind: str = "") -> Item:
    it = Item(审核项="专项评价数量上限", 类别="技术导则符合性")
    if applied_kind and applied_kind != "报告表":
        it.适用 = False
        it.AI审核 = S_NA
        it.置信度 = "高"
        it.理由 = (f"「专项评价」是《报告表编制技术指南（污染影响类）》的概念；"
                   f"本报告为「{applied_kind}」，不适用该数量上限规定。")
        return it
    stated = ex.special_stated or {}
    if not stated:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = ("报告未给出「专项评价设置情况」表，无法核对专项评价数量是否符合"
                   "「一般不超过两项（印刷电路板制造类不超过三项）」的要求，需人工确认。")
        it.需人工确认.append("未找到报告自述的专项评价设置情况表")
        return it
    on = [k for k, v in stated.items() if v.get("set")]
    quota = 3 if re.search(r"印刷电路板", str(ex.basic.get("项目名称") or "")) else 2
    it.判据轨迹 = {"报告自述设置的专项评价": on, "上限": quota,
                   "判据出处": "《报告表编制技术指南（污染影响类）（试行）》表1 注：一般不超过两项"}
    it.参考依据 = f"{GUIDE}表1 注：专项评价一般不超过两项（印刷电路板制造类建设项目不超过三项）"
    if len(on) > quota:
        it.AI审核 = S_SUGGEST
        it.理由 = (f"报告自述设置 {len(on)} 项专项评价（{'、'.join(on)}），"
                   f"超过「一般不超过 {quota} 项」的指引，请核实是否均为必需（从严设置不构成违规）。")
    else:
        it.AI审核 = S_OK
        it.置信度 = "中"
        it.理由 = f"报告自述设置 {len(on) or '0'} 项专项评价，未超过上限 {quota} 项。"
    return it


# ---------------------------------------------------------------- 11：风险物质识别完整性
SOLID_RX = re.compile(r"废|灰|渣|污泥|渗滤液|液$|尘")


def judge_risk_identification(rep, ex, C) -> Item:
    it = Item(审核项="风险物质识别完整性", 类别="环境风险（HJ 169）")
    mats = ex.risk_materials or []
    it.参考依据 = ("《建设项目环境风险评价技术导则》（HJ 169-2018）附录B 表B.1 "
                   "突发环境事件风险物质及临界量清单（385 种）")
    if not mats:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "报告未给出可识别的风险物质/危险物质清单，无法核对识别是否完整，需人工确认。"
        it.需人工确认.append("未抽到风险物质表")
        return it

    hit, solid, unknown = [], [], []
    for m in mats:
        s = C.substance_threshold(m.get("名称", ""), m.get("cas") or "")
        if s:
            hit.append((m, s))
        elif SOLID_RX.search(str(m.get("名称") or "")):
            solid.append(m)
        else:
            unknown.append(m)
    it.判据轨迹 = {"表B.1命中": [(m["名称"], s["name"], s["threshold_t"]) for m, s in hit],
                   "固废类（从严列入，表B.1 无对应）": [m["名称"] for m in solid],
                   "无法对应": [m["名称"] for m in unknown]}
    for m, s in hit[:6]:
        it.证据.append(_ev(m.get("页码"), m.get("原文", ""),
                           f"{m['名称']} → 表B.1「{s['name']}」临界量 {s['threshold_t']:g}t"))
    if unknown:
        it.AI审核 = S_SUSPECT
        it.置信度 = "中"
        it.理由 = (f"报告列 {len(mats)} 项，其中 {len(hit)} 项可在 HJ 169 表B.1 对应、"
                   f"{len(solid)} 项属固废类（从严列入，表B.1 无对应物质，不影响判定）；"
                   f"**{len(unknown)} 项无法对应**（{'、'.join(str(m['名称']) for m in unknown)}），"
                   f"无法机械核对临界量，需人工确认。")
        it.需人工确认.append(
            "表B.1 未列物质：" + "、".join(str(m["名称"]) for m in unknown)
            + "（HJ 169 表B.1 数据源自 HJ 941-2018 附录A，需该附录才能核对）")
    else:
        it.AI审核 = S_OK
        it.置信度 = "中"
        it.理由 = (f"报告列 {len(mats)} 项，均可在 HJ 169 表B.1 对应或属固废类从严列入，"
                   f"识别无明显缺项（完整性以报告自述清单为限）。")
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    return it


# ---------------------------------------------------------------- 12：临界量引用正确性
def judge_risk_threshold(rep, ex, C) -> Item:
    it = Item(审核项="风险物质临界量引用正确性", 类别="环境风险（HJ 169）")
    it.参考依据 = ("《建设项目环境风险评价技术导则》（HJ 169-2018）附录B 表B.1："
                   "危险物质临界量（t）")
    rows = [m for m in (ex.risk_materials or []) if m.get("临界量t") is not None]
    if not rows:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "报告未给出风险物质的临界量数值，无法核对引用是否正确，需人工确认。"
        it.需人工确认.append("风险物质表未列临界量")
        return it
    ok, bad, unknown = [], [], []
    for m in rows:
        s = C.substance_threshold(m.get("名称", ""), m.get("cas") or "")
        if not s:
            unknown.append((m, None))
            continue
        same = abs(float(m["临界量t"]) - float(s["threshold_t"])) < 1e-9
        (ok if same else bad).append((m, s))
    it.判据轨迹 = {"逐项比对": [
        {"报告物质": m["名称"], "报告临界量t": m["临界量t"],
         "表B.1物质": (s["name"] if s else None),
         "表B.1临界量t": (s["threshold_t"] if s else None),
         "页码": m.get("页码"), "一致": bool(s) and abs(float(m["临界量t"]) - s["threshold_t"]) < 1e-9}
        for m, s in (ok + bad + unknown)]}
    for m, s in (bad + ok)[:8]:
        it.证据.append(_ev(m.get("页码"), m.get("原文", ""),
                           f"{m['名称']}：报告 {m['临界量t']:g}t vs 表B.1 {s['threshold_t']:g}t"))
    if bad:
        it.AI审核 = S_PROBLEM
        it.置信度 = "高"
        it.理由 = ("与 HJ 169 表B.1 不一致：" + "；".join(
            f"{m['名称']} 报告 {m['临界量t']:g}t ≠ 表B.1 {s['threshold_t']:g}t" for m, s in bad))
    elif unknown and len(unknown) == len(rows):
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "所引临界量均无法在表B.1 对应，无法核对，需人工确认。"
        it.需人工确认.append("表B.1 未列物质：" + "、".join(m["名称"] for m, _ in unknown))
    else:
        it.AI审核 = S_OK
        it.置信度 = "高" if len(ok) >= 3 else "中"
        it.理由 = (f"核对了 {len(ok)} 项临界量，与 HJ 169 表B.1 一致"
                   + (f"；另有 {len(unknown)} 项表B.1 未列（{ '、'.join(m['名称'] for m, _ in unknown) }），"
                      f"无法核对，需人工确认。" if unknown else "。"))
        if unknown:
            it.需人工确认.append("表B.1 未列物质：" + "、".join(m["名称"] for m, _ in unknown))
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    return it


# ---------------------------------------------------------------- 13：Q 值计算正确性
Q_RX = re.compile(r"Q\s*[=＝]\s*([0-9]+(?:\.[0-9]+)?)")


def judge_risk_q_calc(rep, ex, C, merged: dict) -> Item:
    it = Item(审核项="风险物质 Q 值计算正确性", 类别="环境风险（HJ 169）")
    it.参考依据 = ("《建设项目环境风险评价技术导则》（HJ 169-2018）附录C："
                   "Q = Σ(qi/Qi)，qi 为最大存在总量、Qi 为临界量")
    rows = [m for m in (ex.risk_materials or []) if C.substance_threshold(
        m.get("名称", ""), m.get("cas") or "")]
    if not rows:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "无法在表B.1 对应任何风险物质，Q 值无法复算，需人工确认。"
        return it

    # 复算：只累加"既有贮存量又有临界量"的物质（HJ 169 的 Q 只计贮存量）
    terms, total, lack = [], 0.0, []
    for m in rows:
        s = C.substance_threshold(m.get("名称", ""), m.get("cas") or "")
        q = m.get("最大贮存量t")
        if q is None:
            lack.append(m["名称"])
            continue
        try:
            qi = float(str(q).split("t")[0])
        except Exception:
            lack.append(m["名称"])
            continue
        terms.append(f"{m['名称']} {qi:g}/{s['threshold_t']:g}")
        total += qi / float(s["threshold_t"])
    # 报告自述的 Q（同一页表格末尾的 "Q=x.xxx"）
    page = rows[0].get("页码")
    stated = None
    if page:
        txt = rep.page_text[page - 1] if page - 1 < len(rep.page_text) else ""
        hits = [float(m.group(1)) for m in Q_RX.finditer(txt.replace(" ", ""))]
        stated = hits[0] if hits else None
    it.判据轨迹 = {"逐项 q/Q": terms, "缺贮存量的物质": lack,
                   "复算 ΣQ": round(total, 6), "报告自述 Q": stated, "页码": page}
    if page:
        it.证据.append(_ev(page, rep.page_text[page - 1][
            max(0, rep.page_text[page - 1].find("Q=") - 120):
            rep.page_text[page - 1].find("Q=") + 40] if "Q=" in rep.page_text[page - 1] else "",
            "风险物质表及其 Q 值（来源 表格/原文）"))
    if stated is None:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"按表列数据复算 ΣQ={total:.3f}（{'；'.join(terms) or '无贮存量可算'}），"
                   f"但报告未给出 Q 值，无法比对，需人工确认。")
        it.需人工确认.append("报告未给出 Q 值")
    elif terms and stated + 1e-9 < max(
            [float(t.split()[1].split("/")[0]) / float(t.split("/")[1]) for t in terms] or [0]):
        it.AI审核 = S_PROBLEM
        it.置信度 = "高"
        it.理由 = (f"报告所给 Q={stated:g} **小于其中单项的 q/Q**（{'；'.join(terms)}），"
                   f"ΣQ 不可能小于任一项，数据自相矛盾；按表列数据复算应为 {total:.3f}。"
                   f"（注：不影响「Q<1 故潜势Ⅰ级」的结论方向，但数值须更正。）")
    elif abs(stated - total) > max(0.005, 0.05 * max(total, 1e-9)):
        it.AI审核 = S_SUSPECT
        it.置信度 = "中"
        it.理由 = (f"报告所给 Q={stated:g}，按表列数据复算为 {total:.3f}，两者不一致"
                   f"（{'；'.join(terms)}），需人工核实。")
    else:
        it.AI审核 = S_OK
        it.置信度 = "高"
        it.理由 = f"报告 Q={stated:g} 与按表列数据复算的 ΣQ={total:.3f} 一致。"
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    return it


# ---------------------------------------------------------------- 14：潜势与评价等级
# 罗马数字两种写法都要认：报告里「潜势为I」用的是 ASCII 的 I，
# 只认 Unicode Ⅰ 会让整项误判成"没写"（实测踩坑）。
ROMAN = "ⅠⅡⅢⅣIVXivx+"
POT_RX = re.compile(r"潜势[为是]?\s*([" + ROMAN + r"]{1,3})\s*级?")
M_RX = re.compile(r"(?:M\s*[=＝]\s*)?M([1-4])\b")
E_RX = re.compile(r"(?:E\s*[=＝]\s*)?E([1-3])\b")
LEVEL_RX = re.compile(r"评价(?:工作)?等级[为是]?\s*(一级|二级|三级|简单分析)")
_ROMAN_NORM = {"IV": "Ⅳ", "III": "Ⅲ", "II": "Ⅱ", "I": "Ⅰ", "IV+": "Ⅳ+",
               "iv": "", "iii": "Ⅲ", "ii": "Ⅱ", "i": "Ⅰ", "x": "Ⅹ"}


def _norm_roman(s: str) -> str:
    s = (s or "").strip()
    return _ROMAN_NORM.get(s, _ROMAN_NORM.get(s.upper(), s))


def judge_risk_potential(rep, ex, C, applied_kind: str) -> Item:
    it = Item(审核项="环境风险潜势与评价等级", 类别="环境风险（HJ 169）")
    it.参考依据 = ("《建设项目环境风险评价技术导则》（HJ 169-2018）表1（评价工作等级划分）、"
                   "表2（环境风险潜势划分）、附录C（Q 值计算）")
    if applied_kind == "报告表" and not ex.special_stated.get("环境风险", {}).get("set"):
        it.适用 = False
        it.AI审核 = S_NA
        it.置信度 = "中"
        it.理由 = "本报告为报告表且未设置环境风险专项评价，按指南不要求开展环境风险潜势判定。"
        return it

    # 找"本项目"的潜势结论句，而不是附录里"当Q<1时潜势为I"的规则句
    pages = []
    for pat in (r"潜势为", r"环境风险潜势", r"Q\s*[<＜]\s*1"):
        for h in rep.search(pat, max_hits=4, ctx=0):
            if h["page"] not in pages:
                pages.append(h["page"])
    txt = "".join(rep.page_text[p - 1] for p in pages)
    flat = txt.replace(" ", "").replace("\u3000", "")
    pot = None
    for m in POT_RX.finditer(flat):
        # 优先「本项目/拟建项目…潜势为X级」这种针对本项目的句子
        head = flat[max(0, m.start() - 40):m.start()]
        if re.search(r"本项目|拟建项目|该项目", head) or "当Q" not in head:
            pot = _norm_roman(m.group(1))
            break
    if pot is None:
        m = POT_RX.search(flat)
        pot = _norm_roman(m.group(1)) if m else None
    lev = LEVEL_RX.search(flat)
    q_zero = re.search(r"Q\s*[<＜]\s*1", flat)
    it.判据轨迹 = {"报告自述潜势": pot, "报告自述评价等级": lev.group(1) if lev else None,
                   "涉及页": pages, "是否自述Q<1": bool(q_zero)}

    if pot and q_zero:
        ok = pot in ("Ⅰ", "I")
        if ok:
            it.AI审核 = S_OK
            it.置信度 = "中"
            it.理由 = ("报告判定 Q<1，据此潜势为Ⅰ级、无需开展环境风险评价，"
                       "与 HJ 169 附录C.1.1「Q<1 时潜势直接为Ⅰ」一致。")
        else:
            it.AI审核 = S_SUSPECT
            it.置信度 = "中"
            it.理由 = (f"报告自述 Q<1，但潜势写作「{pot}」；按附录C.1.1，Q<1 时潜势应为Ⅰ级，"
                       f"需人工核实。")
        if pages:
            p = pages[-1]
            t = rep.page_text[p - 1]
            i = t.replace(" ", "").find("潜势为")
            q = ""
            if i >= 0:
                # 按归一化后的位置回原串附近取一段，保证摘录里能看到该结论
                q = t[max(0, i - 80): i + 60]
            it.证据.append(_ev(p, q or t[-200:], "报告自述的 Q 与潜势结论"))
            it.环评文件 = "-P" + str(p)
    else:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = ("报告未明确给出「Q 值 → 危险性分级 M → 环境敏感程度 E → 潜势 → 评价等级」"
                   "的完整判定链，无法机械复核，需人工按 HJ 169 表1/表2 核对。")
        it.需人工确认.append("缺少 M/E 分级与潜势矩阵判定过程")
    return it


# ---------------------------------------------------------------- 15：环境保护目标表完整性
TARGET_HEAD_RX = re.compile(r"环境保护目标|环境敏感目标|敏感保护目标")
TARGET_COL_WORDS = ("方位", "距离", "人口", "保护对象", "规模", "性质")


def judge_targets_table(rep, ex) -> Item:
    it = Item(审核项="环境保护目标表完整性", 类别="报告质量")
    it.参考依据 = ("《报告表编制技术指南（污染影响类）（试行）》表1 注2：环境空气保护目标指"
                   "自然保护区、风景名胜区、居住区、文化区和农村地区中人群较集中的区域；"
                   "报告应给出保护目标的方位、距离与规模")
    # 表名常在**表格外的题注**里（"表2.4-2 拟建项目环境保护目标一览表"），
    # 而"方位/距离"常在第 2 行（合并表头）；只看第 1 行单元格会漏判（实测踩坑）。
    hit, head, cap_page, rows_n = None, "", None, 0
    best = None
    for t in rep.tables:
        rows = t["rows"][:3]
        blob = " ".join(str(c or "") for r in rows for c in r)
        # 至少要有一行**数据行**：只有表头没有数据的表不是环境保护目标表（实测踩坑）。
        # 注意是 >1 而不是 >2 —— 只有 1 个保护目标的报告是合法的，不能因此判"未识别到"。
        if len(t["rows"]) <= 1:
            continue
        name_like = re.search(r"名称|保护对象|敏感点类型", blob)
        pos_like = re.search(r"方位|距离", blob)
        pop_like = re.search(r"户数|人数|规模|人口", blob)
        keyword = re.search(r"保护目标|敏感目标|敏感点", blob)
        # 判据：**名称类列 + 方位/距离列** 是保护目标表的充分特征；
        # 再加"有保护目标字样"或"有人口/规模列"以避免误收其它带方位距离的表。
        # （表名常只写在题注里，所以不能只认"保护目标"四个字。）
        if not (name_like and pos_like and (keyword or pop_like)):
            continue
        best = t
        head = blob
        break
    if best is not None:
        hit, rows_n = best, len(best["rows"]) - 1
    if hit is None:
        # 报告表常在「建设项目基本情况」表里以**一行文字**给出环境保护目标，
        # 没有独立的保护目标表 —— 这种也不能判"未识别到"。
        for t in rep.tables:
            for r in t["rows"]:
                first = str(r[0] or "") if r else ""
                if re.search(r"环境保护目标|敏感保护目标", first):
                    val = " ".join(str(c or "") for c in r[1:])[:200]
                    it.判据轨迹 = {"形式": "基本情况表内文字", "页码": t["page"], "内容": val}
                    it.证据.append(_ev(t["page"], " | ".join(str(c or "") for c in r)[:200],
                                       "环境保护目标（来源 基本情况表）"))
                    it.环评文件 = "-P" + str(t["page"])
                    ok = bool(re.search(r"方位|距离|m|米|无居民|无敏感", val))
                    it.AI审核 = S_OK if ok else S_SUGGEST
                    it.置信度 = "中" if ok else "低"
                    it.理由 = (f"报告以基本情况表内文字给出环境保护目标（P{t['page']}）："
                               f"{val[:80]}"
                               + ("，含方位/距离信息。" if ok else "，未见方位/距离，建议补充。"))
                    if not ok:
                        it.需人工确认.append("保护目标描述是否满足方位/距离要求")
                    return it
    if hit is None:
        cap = rep.search(r"(环境保护目标|环境敏感目标|敏感目标)[^。\n]{0,12}(一览表|表)", max_hits=2)
        if cap:
            cap_page = cap[0]["page"]
            for t in rep.tables:
                if t["page"] == cap_page and len(t["rows"]) > 2:
                    hit = t
                    head = " ".join(str(c or "") for r in t["rows"][:3] for c in r)
                    break
            if hit is None:
                it.判据轨迹 = {"题注页": cap_page, "题注": cap[0]["snippet"][:80]}
                it.证据.append(_ev(cap_page, cap[0]["snippet"], "环境保护目标表题注"))
                it.环评文件 = "-P" + str(cap_page)
                it.AI审核 = S_OK
                it.置信度 = "低"
                it.理由 = (f"报告在 P{cap_page} 给出环境保护目标表题注，"
                           f"但表格结构未能解析（{cap[0]['snippet'][:40]}…），"
                           f"方位/距离等要素需人工核对。")
                it.需人工确认.append("保护目标表结构未解析，需人工核对方位/距离/规模")
                return it
    if hit is None:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "未识别到环境保护目标表，无法核对方位/距离/规模等必备要素，需人工确认。"
        it.需人工确认.append("未抽到环境保护目标表")
        return it
    cols = [w for w in TARGET_COL_WORDS if w in head]
    it.判据轨迹 = {"表头": head[:160], "命中列": cols, "行数": len(hit["rows"]) - 1,
                   "页码": hit["page"]}
    it.证据.append(_ev(hit["page"], head[:200], "环境保护目标表表头"))
    it.环评文件 = "-P" + str(hit["page"])
    missing = [w for w in ("方位", "距离") if w not in head]
    if missing:
        it.AI审核 = S_SUGGEST
        it.置信度 = "中"
        it.理由 = (f"环境保护目标表存在（{len(hit['rows']) - 1} 行），表头含 {'、'.join(cols)}，"
                   f"但未含 {'、'.join(missing)} —— 建议核对是否在别处以文字给出。")
    else:
        it.AI审核 = S_OK
        it.置信度 = "中"
        it.理由 = (f"环境保护目标表存在（{len(hit['rows']) - 1} 行），表头含方位与距离等要素"
                   f"（{'、'.join(cols)}）。")
    return it


# ---------------------------------------------------------------- 16：编制要素完整性
# 每个要素给**多个同义关键词**：报告章节名千差万别（临沂用"1.1 企业概况"，
# 没有"建设项目概况"这个词），只认一个写法会把存在的章节判成缺项。
REQUIRED_BOOK = [
    ("项目概况", ["项目概况", "企业概况", "建设项目概况", "工程概况", "概述"]),
    ("工程分析", ["工程分析", "工艺流程", "工艺分析", "工程内容"]),
    ("污染源", ["污染源", "源强", "污染物排放量", "排放源", "产污环节"]),
    ("环境影响预测", ["环境影响预测", "影响预测与评价", "预测与评价", "环境影响分析"]),
    ("环境风险", ["环境风险"]),
    ("环境保护措施", ["环境保护措施", "污染防治措施", "环保措施", "治理措施", "防治措施"]),
    ("结论", ["结论", "总结"]),
]
REQUIRED_FORM = [
    ("项目概况", ["建设项目基本情况", "项目概况", "工程概况"]),
    ("工程分析", ["工程分析", "工艺流程", "工程内容"]),
    ("污染源", ["污染物排放量", "污染源", "源强", "产污环节"]),
    ("环境保护措施", ["环境保护措施", "污染防治措施", "环保措施", "治理措施"]),
    ("结论", ["结论", "总结"]),
]
# 章节标题形态：**标题行里必须含该要素词**才认（"第3章 工程分析"、"3.2 污染源"）。
# 只判断"这页有没有编号标题"太松 —— 概述章每页都有编号小标题，会把概述页
# 误当成各要素章节（实测踩坑）。
def _titled_pages(rep, kw: str, hits: list) -> list:
    """返回"标题行里含该要素词"的页，**章级标题优先于节级标题**。

    章级："第11章 环境风险评价"  → 这才是该要素的正式章节（临沂环境风险章在 P176）。
    节级："3.2 污染源"            → 报告没给独立章时的次优选择。
    只判断"这页有没有编号标题"太松，概述章每页都有编号小标题，会把概述页
    （P7/P9）误当成各要素章节 —— 实测踩坑，所以标题行必须含要素词。
    """
    chap = re.compile(r"第\s*\d+\s*章[^\n]{0,16}" + re.escape(kw))
    sect = re.compile(r"\d+(?:\.\d+)*\s*[^\n]{0,14}" + re.escape(kw))
    at_chap = [p for p in hits if chap.search(rep.page_text[p - 1])]
    at_sect = [p for p in hits if sect.search(rep.page_text[p - 1])]
    return at_chap or at_sect


def judge_completeness(rep, ex, applied_kind: str) -> Item:
    it = Item(审核项="编制要素完整性", 类别="报告质量")
    need = REQUIRED_BOOK if applied_kind != "报告表" else REQUIRED_FORM
    it.参考依据 = ("《建设项目环境影响报告书（表）编制监督管理办法》及配套指南："
                   "报告应包含工程分析、污染源强、环境影响预测、环境保护措施、结论等要素")
    found, missing = [], []
    for anchor, kws in need:
        pg = None
        for kw in kws:
            # 候选页要给够：只取前几个命中时，命中的全是概述/总论里的提法，
            # 真正的章节页（环境风险 P176、结论 P273）根本进不了候选 —— 实测踩坑。
            hits = [h["page"] for h in rep.search(re.escape(kw), max_hits=40, ctx=0)]
            if not hits:
                hits = [h["page"] for h in rep.anchors.get(kw, [])]
            # 优先"标题行里含该要素词"的那一页；章节标题的**首次**出现处才是该章起点
            # （取最后一次会把正文里提到"概述"的地方当成"项目概况"章节，实测踩坑）
            titled = _titled_pages(rep, kw, hits)
            cand = titled or hits
            if cand:
                pg = cand[0]
                break
        (found if pg else missing).append((anchor, pg))
    it.判据轨迹 = {"报告类型": applied_kind, "已定位要素": found, "未定位要素": missing,
                   "说明": "关键词命中 + 章节标题形态（第N章/N.N）双重确认，取最后一次出现处"}
    for anchor, pg in found[:6]:
        if pg:
            it.证据.append(_ev(pg, f"章节定位：{anchor}", "章节定位（来源 关键词+标题形态）"))
    if it.证据:
        it.环评文件 = "-P" + str(it.证据[0].page)
    if missing:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"按{ '报告书' if applied_kind != '报告表' else '报告表' }要素清单，"
                   f"未定位到：{'、'.join(a for a, _ in missing)}。"
                   f"关键词定位属启发式，**不足以直接判缺项**，需人工确认章节是否以其它名称存在。")
        it.需人工确认.append("未定位要素：" + "、".join(a for a, _ in missing))
    else:
        it.AI审核 = S_OK
        it.置信度 = "中"
        it.理由 = (f"要素清单（{'、'.join(a for a, _ in need)}）均在报告中定位到对应章节"
                   f"（{'；'.join(f'{a} P{p}' for a, p in found)}）。")
    return it


# ---------------------------------------------------------------- 17：引用标准编号正确性 + 现行性
STD_RX = re.compile(r"(HJ\s*/?\s*T?\s*\d{2,5}|GB\s*/?\s*T?\s*\d{4,5})\s*[—\-–~]\s*(\d{2,4})")
# 年份放宽到 2–4 位：老标准常写成两位数年份（GB9137-88、GB3552-83）——
# 原先只认 4 位，这类**引用根本扫不到**（2026-09-23 单测发现）。
# 已知的编号误用（可审计清单）：HJ/T 169-2004 是旧编号，2018 版起为 HJ 169-2018
STD_WRONG = [{"pattern": r"HJ\s*/\s*T\s*169\s*[—\-–~]\s*2018",
              "should": "HJ 169-2018",
              "why": "HJ/T 169-2004 为旧版编号；2018 版发布后编号为 HJ 169-2018（无「/T」）"}]

# ---- A2（2026-09-23）：引用标准"现行性"判据表 -------------------------------------------
# 你的反馈原话：GB3095-2012 格式正常 → 判"编号正确、无问题"，但它已被 GB3095-2026 替代。
# 数据在判据目录的 `标准现行性.json`（本轮落到 /data/fagui_rag/criteria/，由
# `_脚本代码/审核智能体/服务端/建标准现行性.py` 生成；每条带外部依据与"硬度"）。
# **纪律**：表里没有的标准本项一律不判（只说"未收录"）；标"软-待核"的只提示"未核实"，
# 不写断言 —— 这一项最怕"说错了"。
_STD_TABLE = None


def _norm_std(s: str) -> str:
    """标准号归一：统一破折号、去掉空白与斜杠。
    GB 3095—2012 / GB3095-2012 / GB 3095–2012 → GB30952012；GB/T 18883-2002 → GBT188832002。"""
    t = str(s or "").upper()
    for a in ("—", "–", "－", "~", "～"):
        t = t.replace(a, "-")
    return re.sub(r"[\s\-/]", "", t)


def _std_table() -> dict:
    """读判据表（懒加载 + 进程内缓存）。表不存在 → 返回 {}，本项退回"只查编号写法"。"""
    global _STD_TABLE
    if _STD_TABLE is not None:
        return _STD_TABLE
    import json
    import os
    from audit.criteria import DEFAULT_DIR
    d = os.environ.get("EIA_CRITERIA_DIR") or DEFAULT_DIR
    out = {"_meta": {"更新于": "", "条数": 0, "不一致": {}, "装入": False}}
    try:
        with open(os.path.join(d, "标准现行性.json"), encoding="utf-8") as fh:
            raw = json.load(fh)
    except Exception:                                              # noqa: BLE001
        _STD_TABLE = out
        return out
    n = 0
    for e in (raw.get("条目") or []):
        k = _norm_std(e.get("标准号"))
        if k:
            out.setdefault(k, []).append(e)
            n += 1
    out["_meta"] = {"更新于": str(raw.get("生成时间") or ""), "条数": n, "装入": True,
                    "标准数": len([k for k in out if k != "_meta"]),
                    "不一致": {str(x.get("标题") or ""): str(x.get("不一致") or "")
                             for x in (raw.get("库内不一致清单") or [])}}
    _STD_TABLE = out
    return out


def _std_validity(rep) -> tuple:
    """扫报告里引用的标准号，与判据表比对。返回 (需核实清单, 覆盖说明)。"""
    table = _std_table()
    meta = table.get("_meta") or {}
    if not meta.get("装入") or not meta.get("条数"):
        return [], ("判据库未装入「标准现行性」表，本项只核对编号写法"
                    "（表放在判据目录的 标准现行性.json）。")
    rows, seen = [], set()
    pri = {"硬-官方": 0, "硬-标准自身": 1, "软-待核": 2}
    for h in rep.search(STD_RX, max_hits=300, ctx=0):
        m = STD_RX.search(h.get("snippet") or "")
        if not m:
            continue
        key = _norm_std(m.group(0))
        if key in seen:
            continue
        entries = table.get(key) or []
        if not entries:
            continue
        seen.add(key)
        # 同一标准号在表里可能有多条（同一标准的不同 bundle 目录，如 GB 3095—2012 有 3 块/13 块两份）。
        # 合并成一行：优先"硬-官方且写明替代关系"的那条；状态不一致时在结论里点出来。
        e = sorted(entries, key=lambda x: (pri.get(str(x.get("依据硬度") or ""), 3),
                                           0 if (str(x.get("替代") or "").strip()
                                                 and "未查到" not in str(x.get("替代") or "")) else 1))[0]
        title = str(e.get("标题") or "")
        hard = str(e.get("依据硬度") or "")
        state = str(e.get("库内状态") or "")
        repl = str(e.get("替代") or "").strip()
        row = {"标准号": m.group(0), "页码": h.get("page"), "标题": title,
               "判据库状态": state, "替代": repl, "依据硬度": hard,
               "同类条目数": len(entries),
               "外部依据": str(e.get("外部依据") or "")[:200]}
        if title and title in (meta.get("不一致") or {}):
            row["结论"] = "判据库内部口径不一致——" + (meta["不一致"][title] or "")
        elif hard == "软-待核":
            row["结论"] = "现行性未核实（判据库标注「待核」，未联网核实）→ 需人工核对"
        elif state in ("已废止", "废止") or (repl and "未查到" not in repl):
            row["结论"] = "据判据库（更新于 %s），该标准%s，请核实是否仍应作为依据" % (
                meta.get("更新于") or "?",
                ("已被 " + repl + " 代替") if (repl and "未查到" not in repl) else "已废止")
        else:
            continue
        states = sorted({str(x.get("库内状态") or "") for x in entries})
        if len(states) > 1:
            row["结论"] += "（表内同号条目状态不一：%s，请人工核对）" % "、".join(states)
        rows.append(row)
    cov = ("判据库覆盖 %d 条标准现行性记录（%d 个标准号，更新于 %s，逐条带外部依据）；"
           "**表里没有的标准本项不判**，请人工核对。"
           % (meta.get("条数"), meta.get("标准数") or meta.get("条数"), meta.get("更新于") or "?"))
    return rows, cov


def judge_standard_citations(rep, ex) -> Item:
    it = Item(审核项="引用标准编号正确性", 类别="报告质量")
    it.参考依据 = ("判据库已入库标准文本的正式编号（如《建设项目环境风险评价技术导则》HJ 169-2018）；"
                   "以及判据库「标准现行性」表（标准号 → 状态/替代关系/外部依据）")
    found = []
    for w in STD_WRONG:
        hits = rep.search(w["pattern"], max_hits=3, ctx=0)
        for h in hits:
            found.append((w, h))
    seen = {}
    for w in STD_WRONG:
        for h in rep.search(w["pattern"], max_hits=3, ctx=0):
            seen[h["page"]] = (w, h)
    found = list(seen.values())
    stale, cov = _std_validity(rep)
    it.判据轨迹 = {"检出编号误用": [{"页码": h["page"], "应为": w["should"], "原因": w["why"],
                                "原文": h["snippet"][:120]} for w, h in found],
                   "引用标准现行性待核实": stale,
                   "覆盖说明": cov}
    for w, h in found[:4]:
        it.证据.append(_ev(h["page"], h["snippet"], f"应写作 {w['should']}"))
    for r in stale[:4]:
        it.证据.append(_ev(r["页码"], f"{r['标准号']} {r['标题']}".strip(), "标准现行性：" + r["结论"]))
    if found or stale:
        it.AI审核 = S_SUGGEST
        it.置信度 = "高" if (found or any(r["依据硬度"] == "硬-官方" for r in stale)) else "中"
        parts = []
        if found:
            parts.append("发现标准编号误用：" + "；".join(
                f"P{h['page']} 引作「{h['snippet'][:40]}」，应为 {w['should']}（{w['why']}）"
                for w, h in found) + "。属编校问题，建议更正")
        if stale:
            parts.append("引用标准的现行性需核实：" + "；".join(
                f"P{r['页码']} 引「{r['标准号']}」（{r['标题']}）—— {r['结论']}"
                for r in stale[:6]))
        it.理由 = "。".join(parts) + "。" + cov
        if found:
            it.环评文件 = "-P" + str(found[0][1]["page"])
        elif stale and stale[0].get("页码"):
            it.环评文件 = "-P" + str(stale[0]["页码"])
        for r in stale[:6]:
            if r["结论"].startswith("现行性未核实"):
                it.需人工确认.append(f"{r['标准号']} 现行性未核实（判据库标注待核）")
            elif r["结论"].startswith("判据库内部口径不一致"):
                it.需人工确认.append(f"{r['标准号']} 是否整体废止存疑（判据库口径不一致）")
            else:
                it.需人工确认.append(f"{r['标准号']} 是否已被替代、是否仍应作为依据")
    else:
        it.AI审核 = S_OK
        it.置信度 = "低"
        it.理由 = ("未检出已知的标准编号误用，也未检出判据库登记的「已废止/已被替代」引用"
                   "（本项只覆盖判据库中登记的已知模式，不等于标准引用全部正确）。" + cov)
    return it


# ---------------------------------------------------------------- 18：结论与主要问题响应
def judge_conclusion(rep, ex) -> Item:
    it = Item(审核项="结论章节与主要问题响应", 类别="报告质量")
    it.参考依据 = "《建设项目环境影响报告书（表）编制监督管理办法》：结论应明确项目环境影响可行性并回应已识别的主要环境问题"
    # 结论锚点在**概述章**也会命中（临沂 P7 是第1章概述里的"结论"字样），
    # 必须挑"像结论章"的那一页：有章节标题形态、且位置靠后。
    cands = [h["page"] for h in rep.anchors.get("结论", [])]
    cands += [h["page"] for h in rep.search(r"结论", max_hits=40, ctx=0)]
    cands = sorted(set(cands))
    total = rep.pages

    def score(p):
        head = rep.page_text[p - 1][:500]
        s = 0
        if re.search(r"第\s*\d+\s*章[^\n]{0,10}结论", head):
            s += 4
        if re.search(r"^\s*\d+(?:\.\d+)*\s*结论", head, re.M):
            s += 3
        if re.search(r"结论与建议|结论及建议|结论$", head, re.M):
            s += 2
        s += 2 if p > 0.6 * total else 0
        return s
    pg = max(cands, key=score) if cands else None
    if pg is None:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = "未定位到结论章节，无法核对结论与主要环境问题的对应关系，需人工确认。"
        it.需人工确认.append("未定位到结论章节")
        return it
    txt = rep.page_text[pg - 1]
    # 可行性结论常不在结论章首页（临沂 P273 是章首，结论表述在后续页），
    # 所以在结论章范围内（首页起连续若干页）找，并引**找到的那一页**。
    span = list(range(pg, min(pg + 10, rep.pages + 1)))
    verdict, vpage, vtxt = None, pg, txt
    for p in span:
        t = rep.page_text[p - 1]
        m = re.search(r"(不可行|从环境保护角度[^。]{0,20}可行|项目建设可行|环境可行|可行)", t)
        if m:
            verdict, vpage, vtxt = m, p, t
            break
    it.判据轨迹 = {"候选页": cands[-6:], "选定页": pg, "评分": score(pg),
                   "结论表述页": vpage if verdict else None,
                   "是否含明确结论表述": bool(verdict)}
    it.证据.append(_ev(vpage, vtxt[:200], "结论章节"))
    it.环评文件 = "-P" + str(vpage)
    if verdict:
        it.AI审核 = S_OK
        it.置信度 = "中"
        it.理由 = (f"结论章节存在（P{pg} 起）并含明确结论表述"
                   f"（P{vpage}：「{verdict.group(1)}」）。结论与已识别问题的逐条对应关系需人工复核。")
        it.需人工确认.append("结论是否逐条回应了审核发现的问题，需人工复核")
    else:
        it.AI审核 = S_SUSPECT
        it.置信度 = "低"
        it.理由 = (f"结论章节存在（P{pg}），但在 P{pg}-P{span[-1]} 范围内未见明确的可行性"
                   f"结论表述，需人工确认。")
    return it