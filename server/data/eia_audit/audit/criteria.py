#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""③ 判据层：法规 → 可执行判据（代码直接读 JSON，不走 RAG 检索）。

为什么代码读 JSON：
  审核结论必须**可复现、可审计**。检索只能回答"判据长什么样"，不能拿来做判定。

本层的机械边界（重要，不要说过头）：
  - **代码只做数值比较与集合判断**：阈值（≥N 吨）、是非（是否直排）、名单（有毒有害名录）、
    比值（q/Q）、矩阵（P×E→潜势→等级）。
  - **术语归属不由代码猜**：报告写"聚氨酯胶水 + 乙酸乙酯作溶剂"，名录写"年用溶剂型胶粘剂"，
    字符串匹配接不上。归属关系必须由抽取层（可含模型）给出，且**必须携带页码与原文**。
  - 事实缺失时**不得**判定为"存在问题"，应降级为"存在疑似问题"（缺证据不等于违规）。

判据文件：判据库/{分类管理名录2021,专项评价设置判据,环境风险判据}.json
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field

def _default_crit_dir() -> str:
    """判据目录：本地在工作区 `判据库/`，服务器在 `/data/fagui_rag/criteria`。

    为什么用"存在即用"而不是改启动脚本：启动脚本的 md5 是冻结的（不得改动），
    所以路径自适应必须写在代码里，靠环境变量(EIA_CRITERIA_DIR)只作覆盖手段。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    cands = [os.environ.get("EIA_CRITERIA_DIR") or "",
             os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(here))), "判据库"),
             "/data/fagui_rag/criteria"]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return cands[1]


DEFAULT_DIR = _default_crit_dir()

# 单位换算（把项目事实的数值折算到判据的单位）。
# 必须按**维度**分组：吨↔千瓦 数值上都"能算"，但物理上无意义，必须拒绝。
def _name_matches(query: str, table_name: str) -> bool:
    """报告里的物质名与表B.1 名称是否算同一个（受约束的子串匹配，见 substance_threshold）。"""
    if not query or not table_name:
        return False
    for a, b in ((query, table_name), (table_name, query)):
        if a not in b:
            continue
        if re.fullmatch(r"[A-Za-z0-9\-]+", a):
            # 纯拉丁：按整词边界，且太短的（<3 字符）一律不认（CO 不能命中 CODCr）
            if len(a) < 3:
                continue
            if re.search(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])", b):
                return True
        elif len(a) >= 2:            # 中文至少 2 字
            return True
    return False


# 名录条目匹配的最低分：低于它说明只是"字面巧合"，此时拒绝给条目（见 find_items）
MIN_ITEM_SCORE = 16
UNIT_DIM = {
    "吨": ("mass", 1.0), "t": ("mass", 1.0), "t/a": ("mass", 1.0),
    "吨/年": ("mass", 1.0), "吨/日": ("mass", 1.0), "吨/小时": ("mass", 1.0),
    "万吨": ("mass", 1e4),
    # C10-③（2026-09-23）：补 kg/千克 —— 原先 UNIT_DIM 里没有它们，用 kg 填报的用量
    # 折不成"吨"，只能被静默丢弃（`decide.py` 的折算就折不动）。
    "千克": ("mass", 1e-3), "kg": ("mass", 1e-3),
    "立方米": ("vol", 1.0), "标立方米": ("vol", 1.0), "万立方米": ("vol", 1e4),
    "万标立方米": ("vol", 1e4), "万标立方米/年": ("vol", 1e4), "平方米": ("area", 1.0),
    "万平方米": ("area", 1e4),
    # C10-①/E1（2026-09-23 修）：原先写成 1.0 —— **1 亩被当成 1 平方米，差 666.7 倍**。
    # 1 亩 = 2000/3 ㎡（≈666.6667）。影响面已实测：名录 173 条里带面积阈值的只有 4 条，
    # 其中唯一用"亩"的海水养殖条目（序号4）阈值与填报**同为亩**、系数两边同时错会相除抵消；
    # 真正会错的是**跨单位**比较 —— 序号 110 学校/福利院/养老院、111 批发零售市场、
    # 121 汽车摩托车维修场所（阈值写"5000平方米"），项目用亩填报时会被判成不满足。
    "亩": ("area", 2000.0 / 3.0),
    "头": ("count", 1.0), "万头": ("count", 1e4), "只": ("count", 1.0),
    "万只": ("count", 1e4), "羽": ("count", 1.0), "万羽": ("count", 1e4),
    "台": ("count", 1.0), "套": ("count", 1.0),
    "公里": ("len", 1.0), "km": ("len", 1.0), "米": ("len", 1.0),
    "千瓦": ("power", 1.0), "kW": ("power", 1.0), "兆瓦": ("power", 1e3),
    "MW": ("power", 1e3), "千伏": ("volt", 1.0), "kV": ("volt", 1.0),
}
UNIT_FACTOR = {k: v[1] for k, v in UNIT_DIM.items()}
_CMP = {"及以上": ">=", "以上": ">=", "不低于": ">=", "大于": ">",
        "及以下": "<=", "以下": "<=", "不超过": "<=", "小于": "<"}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in UNIT_FACTOR), key=len, reverse=True))
# 与数值绑在一起就不该被当作"行业代码"的字符：单位 + 常见量词。
_UNITISH_RX = re.compile(
    r"^\s*(?:%s|人|张|床|个|所|座|辆|艘|条|亿|万|年|月|日)" % _UNIT_ALT)
# 括号里写着"数值+单位"的条目 = 阈值型条目（如「…（建筑面积5000平方米及以上的）」）
_THRESHOLD_PAREN_RX = re.compile(r"[（(][^）)]{0,24}\d+\s*(?:%s)" % _UNIT_ALT)


def industry_codes(category: str) -> list:
    """从名录条目名里取**行业代码**（GB/T 4754 的 3–4 位码），排除阈值数字。

    为什么要有这个函数（2026-09-22 修 C5）：原先 `re.findall(r"(\\d{3,4})")` 一网打尽，
    于是「学校、福利院、养老院（建筑面积 **5000** 平方米及以上的）」把**面积阈值 5000**
    当成了行业代码；而查询串里只要出现「年产 **5000** 吨环氧树脂」，数字一撞就 +60 分
    （最低门槛只有 16 分）—— 实测环氧树脂项目因此被匹配到"学校、福利院、养老院"。
    判据：数字后面紧跟单位/量词的一律不是代码；「2018年版」里的年份同理排除。
    """
    out = []
    for m in re.finditer(r"(?<!\d)(\d{3,4})(?!\d)", category or ""):
        if _UNITISH_RX.match((category or "")[m.end():m.end() + 8]):
            continue
        out.append(m.group(1))
    return out


def code_in_query(code: str, q: str) -> bool:
    """查询串里是否**以代码身份**出现这串数字（反向保护）。

    查询串里的同一串数字若每一处都跟单位绑在一起（如只有「5000 吨/年」），
    就不算行业代码命中 —— 否则条目里的真代码也会跟产量数字撞上。
    """
    for m in re.finditer(r"(?<!\d)" + re.escape(code), q or ""):
        if not _UNITISH_RX.match((q or "")[m.end():m.end() + 8]):
            return True
    return False


def lead_name_tokens(category: str) -> list:
    """阈值型条目的"名称部分"（第一个括号之前、去掉行业代码的那些词）。

    只对 `_THRESHOLD_PAREN_RX` 命中的条目启用。原因：这类条目的行业名在括号之前
    （学校／福利院／养老院、批发／零售市场），修掉"数字撞号"之后它们就再也召不到了 ——
    给名称部分一个够用的权重，让它们**只能凭名字**命中，不能凭数字。
    """
    head = re.split(r"[（(]", category or "")[0]
    out = []
    for part in re.split(r"[；;、，,]", head):
        t = re.sub(r"[\s]*\d{2,4}\*?[\s]*$", "", part).strip()
        t = re.sub(r"^(含|不含|其他)", "", t).strip()
        if len(t) >= 2 and not re.search(r"\d", t):
            out.append(t)
    return out
# 关键词里允许括号（如「年用溶剂型涂料（含稀释剂）」），但不允许数字与分句标点。
# 「单位与比较词之间可以有括号」是必需的：名录原文写「65吨/小时（45.5兆瓦）及以下的」，
# 括号里是同一阈值的兆瓦换算，比较词在其后 —— 不放过括号就会把「及以下」漏掉，
# 于是默认成 ">="，**方向反了**（实测把报告表档的条件按报告书档比对）。
COND_RX = re.compile(
    rf"(?P<kw>[^；;，,。、0-9]{{2,24}}?)\s*"
    rf"(?P<val>\d+(?:\.\d+)?)\s*(?P<unit>{_UNIT_ALT})\s*"
    rf"(?:[（(][^）)]{{0,24}}[）)])?\s*"
    rf"(?P<cmp>及以上|以上|及以下|以下|不低于|不超过|大于|小于)?")


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


@dataclass
class Condition:
    """名录里的一条条件。threshold 型可机械比较；qualitative 型只能标记"需人判/需事实"。"""
    raw: str
    kind: str                     # threshold | qualitative
    keyword: str = ""
    value: float = None
    unit: str = ""
    cmp: str = ""

    def matches_keyword(self, text: str) -> bool:
        if not text:
            return False
        if not self.keyword:
            return False
        k = self.keyword
        # 去掉"年用/年产/新建/扩建"等前缀噪声后做双向包含
        core = re.sub(r"^(年用|年产|年加工|新建|扩建|改建|新增|总)", "", k)
        for t in (k, core):
            if t and (t in text or text in t):
                return True
        return False


def _residue_meaningful(rest: str) -> bool:
    """切掉阈值条件后剩下的"残渣"是否还算一条**独立**要求？

    名录原文常把同一句话写成「燃煤、燃油锅炉总容量65吨/小时（45.5兆瓦）以上的」，
    阈值切走后剩下「燃煤、 （45.5兆瓦）以上的」—— 它既没有独立语义，
    又已被那条阈值条件覆盖，却被当成"定性条件"记了下来。后果是它永远匹配不上
    任何事实 → 该档永远停在 unknown → 名录档级判不出来（实测：锅炉类、玻璃类条目）。

    判定办法：去掉括号内容（单位换算）、单位词与「以上/以下/的/及」这类虚词后，
    还剩不到 3 个实义字 → 认定是碎片，丢弃；真并列要求（如「有电镀工艺的」「使用其他高污染燃料的」）
    会剩下足够实义字，照旧保留。
    """
    t = re.sub(r"[（(][^）)]*[）)]", "", rest or "")
    t = re.sub(_UNIT_ALT, "", t)
    t = re.sub(r"(及以上|及以下|以上|以下|不低于|不超过|大于|小于|的|及|和|或)", "", t)
    # 兜底档与除外情形必须原样保留：判据层靠「其他（…除外）」识别"其余情形均属本档"
    # 以及括号里的排除项（`_tier_state` 用 raw.startswith("其他") 与正则找"除外"）。
    # 它们去掉括号后往往只剩「其他」两个字，若按碎片丢弃，兜底与排除就全失效
    # （实测：单测_判据层 6 项失败）。
    if "其他" in (rest or "") or "除外" in (rest or ""):
        return True
    return len(re.findall(r"[\u4e00-\u9fffA-Za-z]", t)) >= 3


def parse_conditions(text: str) -> list:
    """把条件文本切成条件列表。'/' 或空表示该档不适用。"""
    text = (text or "").strip()
    if text in ("", "/", "—", "-"):
        return []
    out = []
    parts = [p.strip() for p in re.split(r"[；;]", text) if p.strip()]
    for p in parts:
        hits = list(COND_RX.finditer(p))
        if hits:
            for m in hits:
                kw = m.group("kw").strip("，,、（）() 　")
                out.append(Condition(raw=p, kind="threshold", keyword=kw,
                                     value=_num(m.group("val")), unit=m.group("unit"),
                                     cmp=_CMP.get(m.group("cmp") or "", ">=")))
            # 阈值之外还有别的并列要求（如"有电镀工艺的"）→ 单独记为定性条件；
            # 只是同一句阈值的碎片则丢弃（见 _residue_meaningful）
            rest = COND_RX.sub(" ", p).strip(" ，,、")
            if _residue_meaningful(rest):
                out.append(Condition(raw=p, kind="qualitative", keyword=rest))
        else:
            out.append(Condition(raw=p, kind="qualitative", keyword=p))
    return out


def to_unit(value: float, frm: str, to: str):
    """把 value（单位 frm）换算成单位 to；**维度不同或单位未知则返回 None**。"""
    if value is None:
        return None
    if frm == to:
        return value
    a, b = UNIT_DIM.get(frm), UNIT_DIM.get(to)
    if a is None or b is None or a[0] != b[0]:
        return None
    return value * a[1] / b[1]


def compare(value: float, cmp: str, threshold: float) -> bool:
    return {">=": value >= threshold, ">": value > threshold,
            "<=": value <= threshold, "<": value < threshold}[cmp]


@dataclass
class Fact:
    """抽取层给出的项目事实。**page 与 quote 是必填**，否则不得参与判定。

    present=False 表示报告**明确载明不涉及**该事项（如"本项目不属于以再生塑料为原料生产"）。
    没有 present=False 的表达能力，判据层就无法排除报告书档，只能一律返回"不确定"。
    """
    name: str
    value: float = None
    unit: str = ""
    category: str = ""            # 归属到判据用语（由抽取层映射，可含模型）
    page: int = None
    quote: str = ""
    present: bool = True
    extra: dict = field(default_factory=dict)

    @property
    def citable(self) -> bool:
        return bool(self.page) and bool((self.quote or "").strip())


@dataclass
class ConditionResult:
    condition: Condition
    status: str                   # satisfied | not_satisfied | unknown
    detail: str


def eval_condition(cond: Condition, facts: list) -> ConditionResult:
    """对一条名录条件做机械判定。**无对应事实 → unknown（不得判违规）**。"""
    if cond.kind == "qualitative":
        hit = [f for f in facts if f.citable and cond.matches_keyword(f"{f.name} {f.category}")]
        if hit:
            pos = [f for f in hit if f.present]
            if pos:
                return ConditionResult(cond, "satisfied",
                                       f"报告载明：{pos[0].name}（P{pos[0].page}）")
            neg = hit[0]
            return ConditionResult(cond, "not_satisfied",
                                   f"报告明确载明不涉及『{cond.raw}』（P{neg.page}："
                                   f"{neg.quote[:40]}）")
        return ConditionResult(cond, "unknown",
                               f"定性条件『{cond.raw}』需人工核对，抽取层未给出可引证事实")

    cand = [f for f in facts if f.citable and cond.matches_keyword(f"{f.name} {f.category}")]
    if not cand:
        return ConditionResult(cond, "unknown",
                               f"名录条件『{cond.raw}』的关键词『{cond.keyword}』"
                               f"在报告事实中无对应项 → 缺事实，不判违规")
    pos = [f for f in cand if f.present]
    if not pos:
        neg = cand[0]
        return ConditionResult(cond, "not_satisfied",
                               f"报告明确载明不涉及『{cond.keyword}』（P{neg.page}："
                               f"{neg.quote[:40]}）")
    for f in pos:
        v = to_unit(f.value, f.unit, cond.unit)
        if v is None:
            return ConditionResult(cond, "unknown",
                                   f"{f.name} 有事实（P{f.page}）但单位无法换算"
                                   f"（{f.unit or '未给'} ↔ {cond.unit}）")
        ok = compare(v, cond.cmp, cond.value)
        if ok:
            return ConditionResult(cond, "satisfied",
                                   f"{f.name} {f.value}{f.unit} = {v:g}{cond.unit} "
                                   f"{cond.cmp} {cond.value:g}{cond.unit}（P{f.page}）")
    f = cand[0]
    return ConditionResult(cond, "not_satisfied",
                           f"{f.name} {f.value}{f.unit} 未达阈值 {cond.value:g}{cond.unit}（P{f.page}）")


def _tier_state(conds: list, facts: list) -> dict:
    """判断一档（报告书/报告表/登记表）的状态。

    **重要结构**：名录同一格内用「；」分隔的条件是**或**关系
    （如「以再生塑料为原料生产的；有电镀工艺的；年用溶剂型胶粘剂10吨及以上的」），
    不是且关系。故任一条件满足即该档成立。
    兜底档「其他（…除外）」= 其余情形均属该档，但括号里的除外项需另行核对。
    """
    if not conds:
        return {"state": "not_applicable", "residual": False, "conds": [], "hit": None}
    rs = []
    for c in conds:
        # 兜底档「其他（…除外）」不是可匹配的条件，而是"其余情形均属本档"
        if c.kind == "qualitative" and c.raw.strip().startswith("其他"):
            rs.append(ConditionResult(c, "satisfied", f"兜底档：{c.raw}"))
        else:
            rs.append(eval_condition(c, facts))
    detail = [{"raw": r.condition.raw, "kind": r.condition.kind, "status": r.status,
               "detail": r.detail,
               "keyword": r.condition.keyword, "value": r.condition.value,
               "unit": r.condition.unit, "cmp": r.condition.cmp} for r in rs]
    residual = any(c.kind == "qualitative" and c.raw.strip().startswith("其他") for c in conds)
    excl = None
    for c in conds:
        m = re.search(r"[（(]([^）)]*除外[^）)]*)[）)]", c.raw)
        if m:
            excl = m.group(1)
            break
    # 除外情形要机械核一遍：命中除外 → 本档不适用；缺事实 → 结论降级（记 caveat）
    excl_state, excl_detail = None, None
    if excl:
        econds = parse_conditions(re.sub(r"除外", "", excl))
        ers = [eval_condition(c, facts) for c in econds]
        if any(r.status == "satisfied" for r in ers):
            excl_state = "hit"
            excl_detail = "落入除外情形：" + "；".join(r.detail for r in ers if r.status == "satisfied")
        elif any(r.status == "unknown" for r in ers):
            excl_state = "unknown"
            excl_detail = "除外情形无法核实：" + "；".join(r.detail for r in ers if r.status == "unknown")
        else:
            excl_state = "clear"
    if any(r.status == "satisfied" for r in rs):
        hit = next(r for r in rs if r.status == "satisfied")
        return {"state": "satisfied", "residual": residual, "exclusion": excl,
                "exclusion_state": excl_state, "exclusion_detail": excl_detail,
                "conds": detail, "hit": hit.condition.raw, "hit_detail": hit.detail}
    if any(r.status == "unknown" for r in rs):
        return {"state": "unknown", "residual": residual, "exclusion": excl,
                "exclusion_state": excl_state, "exclusion_detail": excl_detail,
                "conds": detail, "hit": None,
                "hit_detail": "；".join(r.detail for r in rs if r.status == "unknown")}
    return {"state": "not_satisfied", "residual": residual, "exclusion": excl,
            "exclusion_state": excl_state, "exclusion_detail": excl_detail,
            "conds": detail, "hit": None,
            "hit_detail": "；".join(r.detail for r in rs)}


class Criteria:
    """判据库（代码直接读 JSON）。"""

    def __init__(self, crit_dir: str = None):
        self.dir = crit_dir or os.environ.get("EIA_CRITERIA_DIR") or DEFAULT_DIR
        self.catalog = self._load("分类管理名录2021.json", [])
        self.special = self._load("专项评价设置判据.json", {})
        self.risk = self._load("环境风险判据.json", {})
        self._prepare()

    def _load(self, name, default):
        p = os.path.join(self.dir, name)
        if not os.path.exists(p):
            print(f"[判据] 缺少 {p}", file=sys.stderr)
            return default
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def _prepare(self):
        for item in self.catalog:
            item["_cond"] = {
                "报告书": parse_conditions(item.get("report_book", "")),
                "报告表": parse_conditions(item.get("report_form", "")),
                "登记表": parse_conditions(item.get("registry", "")),
            }
            # 条目关键词：按分句切开并剥掉行业代码，用于 find_items 打分
            toks = []
            for part in re.split(r"[；;、，,]", item.get("category", "")):
                t = re.sub(r"[\s]*\d{2,4}\*?[\s]*$", "", part).strip()
                t = re.sub(r"^(含|不含|其他)", "", t).strip()
                if len(t) >= 2:
                    toks.append(t)
            item["_tokens"] = toks
            # 行业代码：只认"像代码"的数字（阈值数字不算 —— 见 industry_codes 的说明）
            item["_codes"] = industry_codes(item.get("category", ""))
            # 阈值型条目（括号里是「数值+单位」）额外记住"名称部分"，
            # 让它们靠名字也能被召到（修掉数字撞号后的补救，见 lead_name_tokens）
            item["_lead_tokens"] = (lead_name_tokens(item.get("category", ""))
                                    if _THRESHOLD_PAREN_RX.search(item.get("category", "") or "")
                                    else [])
        self.risk_by_cas = {s["cas"]: s for s in self.risk.get("substances", []) if s.get("cas")}
        self.risk_by_name = {}
        for s in self.risk.get("substances", []):
            self.risk_by_name.setdefault(s["name"], s)

    # ---------------- 分类管理名录 ----------------
    def find_items(self, text: str, top: int = 5) -> list:
        """按项目类别描述在名录里找候选条目。

        打分由三级构成（教训都来自实测）：
          1. **条件原文命中**（权重最高）：报告常在表一自述名录条目与情形，
             如「十九、非金属矿物制品业52.玻璃及玻璃制品（其他玻璃制造）」，
             「其他玻璃制造」正是一条判据条件的原文，一命中即可锁死条目。
             注意报告可能引用**旧版名录序号**（2018 版 52 vs 2021 版 57），
             因此只能按条目名称/条件原文匹配，绝不能按序号匹配。
          2. 条目名称整词命中，长度平方加权。
          3. 行业代码命中。
        全无命中时回退 2-gram（低权重），保证仍有候选，但须人工确认。
        """
        q = text or ""
        scored = []
        for item in self.catalog:
            score, why = 0, []
            for tier in ("报告书", "报告表", "登记表"):
                for c in item["_cond"][tier]:
                    for seg in re.split(r"[；;]", c.raw):
                        seg = seg.strip()
                        if len(seg) >= 4 and seg in q:
                            score += 150 + len(seg) * 3
                            why.append(f"条件原文:{seg}")
                    # 逐字覆盖：把括号与「除外」去掉后，条件基干（如「生活垃圾发电」）
                    # 的每个字都能在查询串里找到 —— 报告常写「生活垃圾**焚烧**发电」，
                    # 字面接不上，但逐字覆盖能接上。只对纯中文、长度适中的基干生效。
                    base = re.sub(r"[（(][^）)]*[）)]", "", c.raw)
                    base = re.sub(r"[；;、，,]", "", base).strip()
                    if 4 <= len(base) <= 12 and not re.search(r"\d", base) \
                            and all(ch in q for ch in base):
                        score += 100 + len(base) * 2
                        why.append(f"条件逐字:{base}")
            for tok in item["_tokens"]:
                if tok in q:
                    score += len(tok) ** 2
                    why.append(tok)
            # 阈值型条目的"名称部分"：短名（学校／批发…）按 len² 只有 4 分、过不了 16 分门槛，
            # 于是它们以前只能靠"数字撞号"被召到。这里给到 18 分（仅这些条目、仅名称词）。
            for tok in item["_lead_tokens"]:
                if tok in q:
                    score += max(18, len(tok) ** 2)
                    why.append("名称:" + tok)
            for code in item["_codes"]:
                if code_in_query(code, q):
                    score += 60
                    why.append("行业代码:" + code)
            scored.append((score, item, why))
        scored.sort(key=lambda x: -x[0])
        self._last_scores = [(s, it["no"], it["category"][:28], w) for s, it, w in scored[:top]]
        # **没有强信号时拒绝猜**：宁可不给条目（审核项降级为"存在疑似问题"），
        # 也不能挑一个看着像的 —— 实测过把生活垃圾焚烧发电报告书匹配到"水泥制造"，
        # 这种错配会输出"自信但错误"的意见，比说"不确定"危险得多。
        if not scored or scored[0][0] < MIN_ITEM_SCORE:
            self._last_scores = self._last_scores[:3]
            return []
        out = [it for s, it, _ in scored[:top]]
        return out

    def decide_env_category(self, items: list, facts: list) -> dict:
        """判定「应编报告书/报告表/登记表」。

        顺序：报告书档成立 → 报告书；否则报告表档成立 → 报告表；再否则登记表。
        - 同一档内多条件是**或**关系；兜底档「其他（…除外）」视为其余情形。
        - 高档出现 unknown 且未成立 → 结论 **无法确定**（不得判违规，应降级为疑似问题）。
        """
        order = ["报告书", "报告表", "登记表"]
        tiers_all = []
        for item in items:
            states = {}
            for tier in order:
                states[tier] = _tier_state(item["_cond"][tier], facts)
                tiers_all.append({"item_no": item["no"], "category": item["category"],
                                  "tier": tier, **{k: v for k, v in states[tier].items()
                                                   if k != "conds"},
                                  "conds": states[tier]["conds"]})
            # 逐档判定
            rb = states["报告书"]
            if rb["state"] == "satisfied":
                return {"decided": True, "tier": "报告书", "item": item,
                        "unknown": False, "tiers": tiers_all, "basis": rb}
            if rb["state"] == "unknown":
                rf = states["报告表"]
                return {"decided": False, "tier": None, "item": item, "unknown": True,
                        "preliminary": "报告书", "residual_ok": rf["state"] == "satisfied",
                        "tiers": tiers_all, "basis": rb}
            for tier in ["报告表", "登记表"]:
                st = states[tier]
                if st["state"] == "satisfied":
                    return {"decided": True, "tier": tier, "item": item, "unknown": False,
                            "tiers": tiers_all, "basis": st,
                            "residual": st["residual"], "exclusion": st.get("exclusion"),
                            "exclusion_state": st.get("exclusion_state"),
                            "exclusion_detail": st.get("exclusion_detail"),
                            "caveat": (st.get("exclusion_detail")
                                       if st.get("exclusion_state") in ("hit", "unknown") else None)}
                if st["state"] == "unknown":
                    return {"decided": False, "tier": None, "item": item, "unknown": True,
                            "preliminary": tier, "tiers": tiers_all, "basis": st}
        return {"decided": False, "tier": None, "item": items[0] if items else None,
                "unknown": True, "tiers": tiers_all,
                "basis": {"hit_detail": "候选条目里没有任何一档可确定（事实不足）"}}

    # ---------------- 专项评价设置（污染影响类） ----------------
    TOXIC = None
    _ALIAS = None

    def toxic_names(self) -> list:
        if self.TOXIC is None:
            tal = self.special.get("toxic_air_list", {})
            self.TOXIC = list(tal.get("names") or [s["name"] for s in tal.get("substances", [])])
        return self.TOXIC

    def eval_special_industrial(self, facts: dict) -> list:
        """facts 的键与判据 inputs 对应。返回每个要素的机械结论。"""
        toxic = self.toxic_names()
        extra = self.special.get("industrial", {}).get("extra_air_substances", [])
        out = []

        # 大气：废气含名录物质（或有毒有害列举物质）∧ 厂界外 500m 内有环境空气保护目标
        pol = facts.get("废气污染物清单") or []
        hit = [p for p in pol if any(t in p or p in t for t in toxic + extra)]
        target = facts.get("厂界外500米内是否有环境空气保护目标")
        # 2026-09-22（用户反馈"证据不足却判符合要求"的同类坑，一起修）：
        # 原写法 `decided if (hit or target is not None)` 有两个"没证据却下否定结论"的出口 ——
        #   ① 废气清单没抽到 → 理由写成"不在《有毒有害大气污染物名录》…内"→ 判符合要求；
        #   ② 清单命中名录物质、但"500米内有无保护目标"没抽到 → 理由写成"无环境空气保护目标"
        #      → 判符合要求。
        # 现在只有**拿到废气清单**才允许下否定结论；命中名录物质时还必须知道保护目标有无。
        if not pol:
            _st = "unknown"
            _why = "废气污染物清单未抽到，无法判断是否含《有毒有害大气污染物名录》及表1列举物质"
        elif not hit:
            _st = "decided"
            _why = ("废气污染物（%s）不在《有毒有害大气污染物名录》及表1列举物质内"
                    % "、".join(pol))
        elif target is None:
            _st = "unknown"
            _why = ("废气含 %s，但厂界外500米内有无环境空气保护目标未抽到，无法定论"
                    % "、".join(hit))
        elif target:
            _st = "decided"
            _why = "废气含 %s 且厂界外500米内有环境空气保护目标" % "、".join(hit)
        else:
            _st = "decided"
            _why = "厂界外500米内无环境空气保护目标"
        out.append({"element": "大气", "set_special": bool(hit) and target is True,
                    "status": _st, "reason": _why})

        # 地表水：新增工业废水直排（非槽罐车外送）或直排的污水集中处理厂
        direct = facts.get("废水是否直排")
        tanker = facts.get("是否槽罐车外送污水处理厂", False)
        w = bool(direct) and (not tanker)
        out.append({"element": "地表水", "set_special": w,
                    "status": "decided" if direct is not None else "unknown",
                    "reason": ("新增工业废水直排" if w else
                               "废水非直排（报告载明纳管/回用）" if direct is False else
                               # 理由措辞刻意避开「废水…直排」这个句式：本模块给出的理由会被写进
                               # 报告/草稿，而抽取层的直排规则会把它读成事实断言 —— 实测形成过
                               # "判据层自己写的话，被自己读成存在问题"的循环。措辞改了，语义没变。
                               "废水去向未抽到，无法定论（缺事实）" if direct is None else
                               f"废水非直排（去向：{facts.get('废水分向', '未给')}）")})

        # 地下水：原则上不开展；涉集中式饮用水水源或特殊地下水资源保护区才开展
        gw = facts.get("是否涉及集中式饮用水水源或特殊地下水资源保护区")
        out.append({"element": "地下水", "set_special": gw is True,
                    "status": "decided" if gw is not None else "unknown",
                    "reason": ("涉及集中式饮用水水源或特殊地下水资源保护区" if gw is True else
                               "不涉及集中式饮用水水源及热水、矿泉水、温泉等特殊地下水资源保护区，"
                               "原则上不开展" if gw is False else
                               "是否涉及饮用水水源/特殊地下水资源保护区未抽到")})

        # 生态（v2 修正）：新增河道取水 ∧ 取水口下游 500m 内有三场一通道
        # AND 条件只要有一项**明确为否**就已定论，不必等另一项 ——
        # 否则"不新增河道取水"的项目会永远停在"事实不足"（实测：锅炉技改类报告表）
        river = facts.get("是否新增河道取水")
        hab = facts.get("取水口下游500米内是否有重要水生生物三场一通道")
        eco_decided = (river is False) or (river is True and hab is not None)
        out.append({"element": "生态", "set_special": (river is True and hab is True),
                    "status": "decided" if eco_decided else "unknown",
                    "reason": ("新增河道取水且取水口下游500米内有三场一通道" if (river and hab)
                               else "本项目不新增河道取水" if river is False
                               else "非新增河道取水或下游500米内无三场一通道")})

        # 海洋
        sea = facts.get("是否直接向海排放污染物的海洋工程")
        out.append({"element": "海洋", "set_special": sea is True,
                    "status": "decided" if sea is not None else "unknown",
                    "reason": "直接向海排放污染物的海洋工程" if sea else "非直接向海排放的海洋工程"})

        # 环境风险：任一危险物质最大存在总量 ≥ 临界量
        risk = self.eval_risk_special(facts.get("危险物质清单") or [])
        out.append(risk)

        # 表1 正文与全局规则
        out.append({"element": "土壤", "set_special": False, "status": "decided",
                    "reason": "表1 正文明确：土壤不开展专项评价"})
        out.append({"element": "声环境", "set_special": False, "status": "decided",
                    "reason": "表1 正文明确：声环境不开展专项评价"})
        return out

    # ---------------- 环境风险（HJ 169 附录B/C + 表2 + 表1） ----------------
    def substance_threshold(self, name: str = "", cas: str = ""):
        """按 CAS 或名称查表B.1 的临界量。

        匹配顺序：CAS → 精确名称 → **别名表**（报告常用缩写，数据在 环境风险判据.json
        的 `aliases` 里，可审计）→ 受约束的子串匹配。

        子串匹配为什么必须加约束（实测踩坑）：
          报告用缩写写风险物质，直接 `name in k or k in name` 会让
          "CO" 命中 "CODCr 浓度≥10000mg/L 的有机废液"、"氨" 命中 "2-氨基异丁烷" ——
          假匹配会直接造出假结论。所以：
            · 短的纯拉丁串（CO/NH3/HCl）**不做子串匹配**，只能靠别名表或 CAS 命中；
            · 拉丁名按**词边界**匹配（防止 CO 命中 CODCr）；
            · 中文名至少 2 字才允许子串。
        """
        name = (name or "").strip()
        if cas and cas in self.risk_by_cas:
            return self.risk_by_cas[cas]
        if not name:
            return None
        if name in self.risk_by_name:
            return self.risk_by_name[name]
        self._alias_index()
        full = self._ALIAS.get(name) or self._ALIAS.get(name.upper()) or self._ALIAS.get(name.lower())
        if full and full in self.risk_by_name:
            return self.risk_by_name[full]
        for k, v in self.risk_by_name.items():
            if _name_matches(name, k):
                return v
        return None

    def _alias_index(self):
        if self._ALIAS is None:
            self._ALIAS = dict(self.risk.get("aliases") or {})

    def eval_risk_special(self, materials: list) -> dict:
        """专项评价设置（环境风险）：存在任一物质 q ≥ 临界量。

        materials: [{"name","cas","q_t"(最大存在总量 t),"page","quote"}]
        表B.1 未列且无表B.2 归类依据 → unknown（不判违规）。
        """
        if not materials:
            # 2026-09-22 用户反馈（江西省博信玻璃项目）：
            #   报告只写"报告未给出危险物质清单，本项目不符合设置条件，报告未设置，符合要求"。
            # 原实现在**空列表**时循环体一次都不执行 → decided 保持 True、any_over 保持 False
            # → 返回"不符合设置条件" → 判据层给"无问题"。这是**把"没有证据"当成"判定为否"**：
            # 报告没列清单 ≠ 项目没有危险品。没有输入就只能说不知道。
            # 实测影响：6 份已审核报告里有 2 条结论属于这个坑（见 查空输入误判.py）。
            return {"element": "环境风险", "set_special": None, "status": "unknown",
                    "reason": "报告未给出危险物质清单（未抽到风险物质及其最大存在总量），"
                              "无法判断是否涉及风险物质",
                    "materials": []}
        detail, decided, any_over = [], True, False
        for m in materials:
            s = self.substance_threshold(m.get("name", ""), m.get("cas", ""))
            q = _num(m.get("q_t"))
            if s is None or q is None:
                decided = False
                detail.append(f"{m.get('name') or m.get('cas')}："
                              f"{'临界量未在表B.1/B.2 中找到' if s is None else '最大存在总量未给'}"
                              f" → 缺判据输入")
                continue
            over = q >= s["threshold_t"]
            any_over = any_over or over
            detail.append(f"{s['name']}：{q:g}t vs 临界量 {s['threshold_t']:g}t "
                          f"→ {'超过' if over else '未超过'}（P{m.get('page', '?')}）")
        return {"element": "环境风险", "set_special": any_over if decided else None,
                "status": "decided" if decided else "unknown",
                "reason": "；".join(detail) or "报告未给出危险物质清单",
                "materials": materials}

    def risk_potential(self, q: float, m_grade: str, e_grade: str) -> dict:
        """Q→P→潜势→评价等级（附录C、表2、表1 机械查表）。"""
        P = self.risk["rules"]["P_危险性分级"]["matrix"]
        if q < 1:
            return {"Q": q, "potential": "Ⅰ", "level": "简单分析",
                    "note": "C.1.1：Q<1 时潜势直接为Ⅰ"}
        q_row = "Q≥100" if q >= 100 else "10≤Q<100" if q >= 10 else "1≤Q<10"
        p_val = P["values"][P["rows"].index(q_row)][P["cols"].index(m_grade)]
        M = self.risk["rules"]["潜势划分"]["matrix"]
        pot = M["values"][M["rows"].index(e_grade)][M["cols"].index(p_val)]
        level = self.risk["rules"]["评价工作等级"]["mapping"]
        lv = ("一级" if pot in ("", "Ⅳ+") else level.get(pot))
        return {"Q": q, "Q_row": q_row, "M": m_grade, "P": p_val,
                "E": e_grade, "potential": pot, "level": lv}

    # ---------------- 生态影响类（报告表） ----------------
    def eval_special_ecological(self, facts_text: str, excluded: list = None) -> list:
        """按「涉及项目类别」列举做关键词匹配。仅用于给出候选结论，仍需页码证据。"""
        out = []
        for rule in self.special.get("ecological", {}).get("rules", []):
            matched = []
            for cond in rule.get("conditions", []):
                blob = facts_text or ""
                if any(x in blob for x in (cond.get("exclude_if") or [])):
                    continue
                if any(k not in blob for k in (cond.get("all_of") or [])):
                    continue
                if cond.get("any_of") and not any(k in blob for k in cond["any_of"]):
                    continue
                if cond.get("and_any_of") and not any(k in blob for k in cond["and_any_of"]):
                    continue
                matched.append(cond["desc"])
            out.append({"element": rule["category"], "set_special": bool(matched),
                        "reason": "；".join(matched) if matched else "未匹配到列举的项目类别",
                        "evidence": rule["evidence"]})
        return out