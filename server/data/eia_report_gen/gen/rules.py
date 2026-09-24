# -*- coding: utf-8 -*-
"""专项评价设置：把**填报表**翻译成判据层要的事实，再交给审核侧同一个求值器。

为什么这里不自己写求值逻辑：审核线已有 `Criteria.eval_special_industrial()`，
它实现了表1 五个要素＋土壤/声环境的全部条件（含 AND 短路、`decided/unknown` 语义）。
生成侧若另写一套，两边迟早会给出不同结论 —— 那是本项目最不能接受的一类 bug
（同一份项目，审核说不该设、生成说该设）。所以这里只做**字段名映射**与数量上限，
其余一律调用同一个函数。

映射表是显式的、可测的：填报表用中文长键（给使用者看），判据用另一套键名。
"""
from __future__ import annotations

# 填报表字段 → 判据事实键（键名必须与 判据库/专项评价设置判据.json 及
# audit/criteria.py 里的 eval_special_industrial 完全一致）
FIELD_TO_FACT = {
    "废气污染物清单": "废气污染物清单",
    "厂界外500m内有环境空气保护目标": "厂界外500米内是否有环境空气保护目标",
    "是否新增工业废水直排": "废水是否直排",
    "是否新增废水直排污水集中处理厂": "是否为污水集中处理厂",
    "是否槽罐车外送污水处理厂": "是否槽罐车外送污水处理厂",
    "是否涉及特殊地下水资源保护区": "是否涉及集中式饮用水水源或特殊地下水资源保护区",
    "是否新增河道取水": "是否新增河道取水",
    "取水口下游500m有三场一通道": "取水口下游500米内是否有重要水生生物三场一通道",
    "是否直接向海排放污染物": "是否直接向海排放污染物的海洋工程",
}


def risk_materials(items: list) -> list:
    """填报表的危险物质 → 判据层要的 {name, cas, q_t}。

    填报用中文键（{名称, 最大贮存量t}）便于填写，判据层用英文键；
    只做映射，不做换算 —— 单位按吨，填报表里已说明。
    """
    out = []
    for m in items or []:
        if not isinstance(m, dict):
            continue
        out.append({"name": m.get("名称") or m.get("name") or "",
                    "cas": m.get("cas") or m.get("CAS") or "",
                    "q_t": m.get("最大贮存量t", m.get("q_t")),
                    "来源": "填报表：危险物质"})
    return out


def facts_from_form(data: dict) -> dict:
    facts = {}
    for mine, theirs in FIELD_TO_FACT.items():
        if mine in data:
            facts[theirs] = data.get(mine)
    facts["危险物质清单"] = risk_materials(data.get("危险物质"))
    return facts


def decide_specials(data: dict, crit) -> dict:
    """返回 {要素: [...], 数量上限: {...}, 冲突: [...], 事实键: {...}}。"""
    facts = facts_from_form(data)
    rows = crit.eval_special_industrial(facts)

    # 水：判据的第二个分支是"新增废水直排的污水集中处理厂"。
    # 审核侧的求值器用「直排 ∧ 非槽罐车外送」覆盖了它（集中处理厂直排即直排）。
    # 但如果填报出现「是集中处理厂、却又不直排」这种自相矛盾，必须点出来而不是忽略。
    conflicts = []
    plant = data.get("是否新增废水直排污水集中处理厂")
    direct = data.get("是否新增工业废水直排")
    if plant is True and direct is False:
        conflicts.append("填报自相矛盾：既是新增废水直排的污水集中处理厂，又填「不直排」——"
                         "请核对废水去向（地表水专项评价按「直排」处理）")

    n_set = sum(1 for r in rows if r.get("set_special") is True)
    n_unknown = sum(1 for r in rows if r.get("status") == "unknown")
    pcb = data.get("是否印刷电路板制造")
    limit = 3 if pcb is True else 2
    quota = {
        "上限": limit,
        "依据": ("印刷电路板制造类建设项目不超过三项" if pcb is True
                 else "专项评价一般不超过两项" + ("（未填是否 PCB，按一般情形）" if pcb is None else "")),
        "已定应设": n_set, "待人工确认": n_unknown,
        "超出": n_set > limit,
        "确定": pcb is not None,
    }
    return {"要素": rows, "数量上限": quota, "冲突": conflicts, "事实键": facts}