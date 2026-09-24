# -*- coding: utf-8 -*-
"""判定层：由**填报表**算出报告该长什么样。

给三件事，全部纯代码、可追溯：
  ① 名录档级：本项目该编报告书/报告表/登记表，依据名录哪一条（调用审核侧同一函数）；
  ② 专项评价设置：该设哪几项、依据表1 哪句（调用审核侧同一函数）；
  ③ 章节与字段清单：从 `判据库/报告表结构.json`（由指南机械导出）取，
     标出每节每个字段是"已填/未填"，未填的不许编。

模型在这一层没有位置 —— 它只在下游写叙述。
"""
from __future__ import annotations

import json
import os
import re

from . import rules

# 项目根目录：本地按包位置推；部署到服务器时用 GEN_HOME 指定（服务器上引擎不在
# 项目树里，推不出来）。判据目录可另用 GEN_CRIT_DIR 覆盖。
WORK = os.environ.get("GEN_HOME") or os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CRIT_DIR = os.environ.get("GEN_CRIT_DIR") or os.path.join(WORK, "判据库")
STRUCT = os.path.join(CRIT_DIR, "报告表结构.json")
STDLIB = os.path.join(CRIT_DIR, "标准引用清单.json")

# 报告表六章必涉及的要素（本工具归类，不是指南原文）：任何工业类项目都要写
# 废气/废水/噪声/固废四类影响与措施，所以先按这四类去语料里找候选标准。
BASE_ELEMENTS = ["废气", "废水", "噪声", "固体废物"]


def load_criteria():
    """复用审核引擎的判据加载（同一套判据文件，不另存一份）。"""
    import sys
    p = os.environ.get("AUDIT_HOME") or os.path.join(WORK, "_脚本代码", "审核智能体")
    if p not in sys.path:
        sys.path.insert(0, p)
    from audit.criteria import Criteria
    return Criteria()


def load_structure() -> dict:
    with open(STRUCT, encoding="utf-8") as f:
        return json.load(f)


def load_standards() -> dict:
    """标准引用清单（由 `_脚本代码/数据采集/建判据_标准引用.py` 从 7 份报告机械抽取）。

    它记的是**语料引用事实**：哪个标准被哪些报告引过、同一段落里在讲什么要素/污染物。
    不是权威的"行业→适用标准"判定 —— 所以生成稿里只能作**候选**并注明须人工核定。
    """
    if not os.path.isfile(STDLIB):
        return {"标准": [], "缺口": "未找到 判据库/标准引用清单.json"}
    with open(STDLIB, encoding="utf-8") as f:
        return json.load(f)


# 通用词（几乎任何工业项目都会命中）权重低；特征词权重高，避免"废气/废水/颗粒物"
# 这种泛匹配把排名冲乱。
GENERIC_WORDS = {"废气", "废水", "噪声", "固体废物", "固废", "颗粒物", "二氧化硫",
                 "氮氧化物", "pH", "色度", "悬浮物"}
SPECIFIC_WEIGHT, GENERIC_WEIGHT = 5, 1

# 标准名称里的特定行业词：标准名称含它、而项目自身（名称/行业类别/产品/原辅料/工艺）
# 完全没提到 → 判为"疑似不适用"，只列进"已排除"而不进候选。
# 为什么必须做这一步：语料 7 份里 5 份是垃圾焚烧报告，只按共现排序会把
# 「生活垃圾焚烧污染控制标准」推给锅炉技改项目 —— 这是语料偏置，不是适用性。
INDUSTRY_HINTS = ["生活垃圾焚烧", "生活垃圾填埋", "垃圾焚烧", "垃圾填埋", "危险废物",
                  "医疗废物", "水泥", "玻璃", "制药", "电镀", "造纸", "印染", "钢铁",
                  "焦化", "火电", "锅炉", "光伏", "电池", "涂装", "家具", "食品"]


def suggest_standards(data: dict, lib: dict, top: int = 8) -> dict:
    """按项目特征词与「标准共现词」的重合度给候选标准（供人工核定）。"""
    feats = set(BASE_ELEMENTS)
    for p in (data.get("废气污染物清单") or []):
        if str(p).strip():
            feats.add(str(p).strip())
    if data.get("危险物质"):
        feats.add("环境风险")
    if data.get("是否涉及特殊地下水资源保护区") is True:
        feats.add("地下水")
    project_text = " ".join(str(x) for x in [
        data.get("项目名称"), data.get("建设项目行业类别"), data.get("国民经济行业类别"),
        data.get("工艺流程简述"),
    ] + [str(x.get("名称")) for x in (data.get("产品及产能") or []) if isinstance(x, dict)]
      + [str(x.get("名称")) for x in (data.get("主要原辅材料") or []) if isinstance(x, dict)])

    rows, dropped = [], []
    for s in (lib.get("标准") or []):
        words = set(s.get("共现要素") or []) | set(s.get("共现污染物") or [])
        hit = sorted(feats & words)
        if not hit:
            continue
        name = s.get("名称") or ""
        # 特定行业词守卫（名称含、项目未提 → 不进候选，记进"已排除"）
        blind = [h for h in INDUSTRY_HINTS if h in name and h not in project_text]
        if blind:
            dropped.append({"标准号": s["标准号"], "名称": name, "原因": "名称含『%s』，项目未涉及" % blind[0],
                            "引用报告数": s.get("引用报告数", 0)})
            continue
        score = sum(SPECIFIC_WEIGHT if w not in GENERIC_WORDS else GENERIC_WEIGHT for w in hit)
        score += min(s.get("引用报告数", 0), 7)
        rows.append({"标准号": s["标准号"], "名称": name,
                     "命中词": hit, "特征命中": [w for w in hit if w not in GENERIC_WORDS],
                     "引用报告数": s.get("引用报告数", 0),
                     "出处": [x.get("报告") for x in (s.get("出处") or [])][:2],
                     "打分": score})
    rows.sort(key=lambda r: (-r["打分"], r["标准号"]))
    return {
        "候选": rows[:top],
        "已排除": sorted(dropped, key=lambda r: -r["引用报告数"])[:6],
        "项目特征词": sorted(feats),
        "性质": "候选来自语料引用的**共现**关系（哪些标准常与这些要素/污染物一起出现），"
                "不是权威适用性判定；已按标准名称里的特定行业词做过一轮排除（见『已排除』）。"
                "采用前仍须人工核定标准号与年份是否现行有效，并补地方标准。",
        "缺口": lib.get("缺口", ""),
    }


# 生成侧的"出处"是**填报表**，没有报告页码。判据层的 Fact.citable 要求 page 为真值
# （`bool(page) and bool(quote)`），所以 0 会被当成"不可引证"而整条事实作废 ——
# 用哨兵 -1 让它成立，输出时再由 _fix_provenance 改写成「填报表」。
# 只改生成侧的显示文本，审核侧代码与其字节级验证过的输出一律不动。
FORM_PAGE = -1


def risk_list(data: dict, crit) -> list:
    """危险物质清单（供草稿出表 + 回修自审）：临界量取自 HJ 169 表B.1，取不到就照实留空。

    取不到不是"没有风险"，而是**判据库里对应不上**（如「天然气」——表B.1 收的是「甲烷」
    CAS 74-82-8、临界量 10t，但没有"天然气"这个别名）→ 状态写"表B.1未对应，须人工核定"，
    不替它填一个数。
    """
    out = []
    for m in (data.get("危险物质") or []):
        if not isinstance(m, dict) or not m.get("名称"):
            continue
        name = str(m["名称"]).strip()
        cas = str(m.get("cas") or "").strip()
        q = m.get("最大贮存量t")
        if q is None:
            q = m.get("最大存在量t")
        s = None
        try:
            s = crit.substance_threshold(name, cas)
        except Exception:                                          # noqa: BLE001
            s = None
        out.append({
            "名称": name, "cas": cas, "最大贮存量t": q,
            "临界量t": (s or {}).get("threshold_t"),
            "表B.1名称": (s or {}).get("name") or "",
            # C8-2 收尾（2026-09-23）：命中表B.1 却**没给最大贮存量**时，原先只写"临界量 Xt"，
            # 看不出这条其实没法判（Q 值算不出来）→ 显式写"未给最大贮存量，须人工核定"。
            "状态": ("表B.1「%s」临界量 %gt；**未给最大贮存量**，Q 值无法计算，须人工核定"
                     % (s["name"], s["threshold_t"])) if (s and q is None)
                    else (("表B.1「%s」临界量 %gt" % (s["name"], s["threshold_t"])) if s
                          else "表B.1 未对应，须人工核定"),
        })
    return out


def material_facts(data: dict) -> list:
    """主要原辅材料 → 判据层事实（**按维度折算成"吨"**）。

    C10-③（2026-09-23 修）：原先这里用白名单 `unit in ("吨","t","t/a","吨/年")` 挑，
    白名单之外的（**万吨、kg、千克**）**被静默丢弃** —— 名录的定量条件于是拿不到这条事实，
    判据层只会说"缺事实"，用户看到的是"判不了"。而 `UNIT_DIM` 里本来就有"万吨"、
    `to_unit()` 也现成，纯粹是没接上。
    现在：折得动就进事实表（并把换算写进 quote，让人看得见），折不动（如"千瓦"）才跳过。
    """
    from audit.criteria import Fact, to_unit
    out = []
    for it in (data.get("主要原辅材料") or []):
        if not isinstance(it, dict):
            continue
        n, u, unit = it.get("名称"), it.get("年用量"), (it.get("单位") or "吨")
        if not n:
            continue
        # 走接口直接提交时，年用量常是**字符串**（页面自带样例里就是 "3000"）。
        # 原先只认 int/float ⇒ 这类填报的用量会被**整体跳过**（又是一处"静默丢数据"）。
        if isinstance(u, str):
            m = re.match(r"\s*([0-9]+(?:\.[0-9]+)?)", u.replace(",", "").strip())
            u = float(m.group(1)) if m else None
        if not isinstance(u, (int, float)):
            continue
        q = to_unit(float(u), unit, "吨")
        if q is None:
            continue
        quo = f"填报表：{n} {u}{unit}"
        if unit not in ("吨", "t", "t/a", "吨/年"):
            quo += f"（折合 {q:g} 吨）"
        out.append(Fact(name="原辅材料用量", value=q, unit="吨", category=n,
                        page=FORM_PAGE, quote=quo))
    return out


def _fix_provenance(text: str) -> str:
    """把判据层打印的报告页码（生成侧哨兵 -1）改写成「填报表」。

    两种出现形态都要处理：`（P-1）` 和 `（P-1：原文）`。
    """
    t = re.sub(r"（P-1）", "（填报表）", text or "")
    return re.sub(r"（P-1([：:])", r"（填报表\1", t)


def decide_category(data: dict, crit) -> dict:
    """名录档级：应编报告书还是报告表。

    复用审核线的 `Criteria.decide_env_category`（与审核报告时**同一段代码**），
    所以不存在"生成说该编报告书、审核说该编报告表"的可能。
    `basis` 是分档状态字典，这里翻译成人能读的理由与逐条条件。
    """
    terms = [data.get("建设项目行业类别") or "", data.get("项目名称") or "",
             data.get("国民经济行业类别") or ""]
    for it in (data.get("产品及产能") or []):
        if isinstance(it, dict):
            terms.append(it.get("名称") or "")
    for it in (data.get("主要原辅材料") or []):
        if isinstance(it, dict):
            terms.append(it.get("名称") or "")
    query = " ".join(t for t in terms if t)
    items = crit.find_items(query, top=5)
    if not items:
        return {"decided": False, "tier": None, "理由": "未能匹配到《分类管理名录》任何条目",
                "候选": [], "逐条条件": [],
                "需人工确认": ["名录条目未匹配：请补填「建设项目行业类别」（照名录原文写）"]}

    # 定量条件用填报表的用量（单位按吨），定性条件由填报的行业类别/产品名体现；
    # 事实不足时 decide_env_category 会返回 unknown —— 那就写"需人工确认"，不猜。
    from audit.criteria import Fact
    facts = material_facts(data)          # C10-③：单位折算已抽成函数（万吨/kg/千克不再丢）
    # 填报者照名录原文写的「建设项目行业类别」本身就是一条**肯定事实**，
    # 与审核线用「报告自述名录情形」定档同一原理：名录的定性条件
    # （如「其他玻璃制造」「有电镀工艺的」）正是靠这句原文匹配上的。
    stated = (data.get("建设项目行业类别") or "").strip()
    if stated:
        facts.append(Fact(name="填报名录情形", present=True, category=stated,
                          page=FORM_PAGE, quote=f"填报表：建设项目行业类别＝{stated}"))
    # 补充事实：判定层报「缺事实」后由人照原文补的定量事实（工具只负责比对，不负责给值）。
    # `不适用: true` 表示填报者**明示本项目不属于该名录情形**（对应审核线抽取层的
    # negation_facts：`present=False`）。名录里同一句条件常同时被解析成定量与定性两条，
    # 定性那条只有靠这条否定事实才能给出"不满足"的定论 —— 工具不替人推断是否适用。
    for it in (data.get("补充事实") or []):
        if not isinstance(it, dict):
            continue
        n, v, unit = it.get("名称"), it.get("值"), (it.get("单位") or "")
        if not n:
            continue
        if it.get("不适用") is True:
            facts.append(Fact(name=n, present=False, category=n, page=FORM_PAGE,
                              quote=f"填报表：补充事实「{n}」填报为不适用"))
        elif isinstance(v, (int, float)):
            facts.append(Fact(name=n, value=float(v), unit=unit, category=n,
                              page=FORM_PAGE, quote=f"填报表：补充事实 {n}={v}{unit}"))
    d = crit.decide_env_category(items, facts)
    item = d["item"] or {}
    basis = d.get("basis") or {}
    tier = d.get("tier")
    conds = [{"条件": c.get("raw"), "结果": c.get("status"), "说明": _fix_provenance(c.get("detail"))}
             for c in (basis.get("conds") or [])]
    ok = bool(d.get("decided")) and tier in ("报告书", "报告表", "登记表")
    理由 = _fix_provenance(basis.get("hit") or basis.get("hit_detail") or "")
    if not 理由:
        理由 = "；".join(c["说明"] for c in conds if "结果" in c) or "名录条件比对未给出明确结论"
    if not ok and d.get("preliminary"):
        理由 += f"（事实不足，倾向档位：{d['preliminary']}）"
    if basis.get("exclusion_state") in ("hit", "unknown"):
        理由 += f"；除外情形：{_fix_provenance(basis.get('exclusion_detail') or '')}"
    return {
        "decided": ok, "tier": tier,
        "状态": "decided" if ok else ("unknown" if d.get("unknown") else "preliminary"),
        "倾向档位": d.get("preliminary"),
        "名录序号": item.get("no"), "名录条目": item.get("category"),
        "报告书条件": item.get("report_book"), "报告表条件": item.get("report_form"),
        "登记表条件": item.get("registry"),
        "理由": 理由, "逐条条件": conds,
        "候选打分": getattr(crit, "_last_scores", [])[:3],
        # 缺哪些事实才能定档：把**条件原文**列出来，让人照着补「补充事实」，
        # 而不是工具替人拍板（这是本工具与自己编造之间的分界线）
        "待补事实": [c["条件"] for c in conds if c["结果"] == "unknown"],
        "需人工确认": ([] if ok else
                       ["名录档级未能唯一确定，请人工核对行业类别与工艺/用量条件"]),
    }


def decide(data: dict, crit=None, structure=None) -> dict:
    crit = crit or load_criteria()
    structure = structure or load_structure()
    cat = decide_category(data, crit)
    spec = rules.decide_specials(data, crit)

    # 章节与字段：把"填报给了没有"逐项标出来，缺的不许编
    filled = {k: v for k, v in data.items() if v not in (None, "", [])}
    plan = structure.get("本工具归类") or {}
    sections = []
    for s in structure.get("章节", []):
        fields = []
        for f in s.get("字段", []):
            way = (plan.get(s["名称"]) or {}).get(f["字段"], "")
            fields.append({"字段": f["字段"], "指南说明": f.get("指南说明", ""),
                           "产出方式": way, "已填": f["字段"] in filled})
        sections.append({"序号": s["序号"], "名称": s["名称"], "表": s.get("表"),
                         "指南页码": s.get("指南页码"), "字段": fields})

    # 危险物质清单：出表用，也是自审"风险物质识别完整性"能否核对的输入
    risks = risk_list(data, crit)
    # 并明确标注性质（共现≠适用），由人工核定。宁可给"候选+须核定"，也不编标准号。
    standards = suggest_standards(data, load_standards())
    need_human = list(cat["需人工确认"])
    for r in spec["要素"]:
        if r.get("status") == "unknown":
            need_human.append(f"{r['element']}专项评价：{r['reason']}")
    need_human += spec["冲突"]
    return {"名录": cat, "专项评价": spec, "章节": sections, "标准": standards,
            "危险物质": risks,
            "需人工确认": need_human,
            "统计": {"应设专项评价": sum(1 for r in spec["要素"] if r.get("set_special") is True),
                     "待人工确认项": len(need_human)}}