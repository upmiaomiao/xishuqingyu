# -*- coding: utf-8 -*-
"""对话式填报：用户自然语言描述项目 → 抽取事实 → 反问缺口 → 汇总成生成输入。

为什么不给用户看填报表：填报字段是**工具内部**的表示（也是为了判定层能机械比对），
要用户照着 JSON 填是把工具的活儿推给用户。这里改成：

    用户说一段话  → ①模型抽取 → ②**代码核验**（用户原话里找不到依据的一律丢弃）
                  → ③判据层算缺口 → ④模型把缺口问成人话 → ⑤用户自由文本回答
                  → 回到 ①（多轮）→ ⑥汇总成 data 交给生成管线

两条不许动摇的规矩：
  · **抽取必须有依据**：模型给的每个值都要能在用户原话（或本轮回答）里找到字面依据，
    否则丢弃并记下"为什么丢"。这就是对话侧的出处闸门。
  · **代码决定问什么**：问哪些问题是判据层算出来的（必填缺项 + 名录/专项的待补事实），
    模型只负责把问题说成人话 —— 模型不问自己想问的。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.environ.get("GEN_HOME") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
AUDIT = os.environ.get("AUDIT_HOME") or os.path.join(WORK, "_脚本代码", "审核智能体")
if AUDIT not in sys.path:
    sys.path.insert(0, AUDIT)

from gen import schema  # noqa: E402

PROMPT_VERSION = "intake-v2"
CACHE_DIR = os.path.join(HERE, "_cache_intake")

# ---------------------------------------------------------------- 提示词

SYSTEM_EXTRACT = (
    "你是环评报告编写助手。用户会用自然语言描述一个建设项目。"
    "你的任务：**只把用户明确说过的信息**填进给定字段，输出 JSON。\n"
    "每个字段的格式是：{\"字段key\": {\"值\": 值, \"原文\": \"用户描述里逐字复制的片段\"}}\n"
    "铁律：\n"
    "1. 绝不用外部知识、绝不推断用户没说的东西；用户没提到的字段**不要出现在 JSON 里**。\n"
    "2. `原文` 必须是从用户描述里**逐字复制**的一段连续文字（可以截取、不可以改写、不可以拼接"
    "不同位置的字），它是这个字段的依据；找不到依据就不要写这个字段。\n"
    "3. `值` 可以替用户整理成规范写法（如把「20吨/小时」写成数值 20、单位 吨/小时；"
    "把「布袋除尘和双碱法脱硫」写成措施内容），但不得添加原文没有的信息。\n"
    "4. 值里出现的每个数字都必须能在 `原文` 里找到。\n"
    "5. 布尔字段给 true/false；列表字段给数组，元素是对象。\n"
    "6. 只输出 JSON，不要解释、不要 markdown 代码块。"
)

SYSTEM_ASK = (
    "你是环评报告编写助手。下面给你若干「需要向用户确认的事项」（每项带字段名与说明）。"
    "请把它们说成**通俗、具体、一次能答**的问题，输出 JSON 数组，每项 "
    "{\"key\": 字段名, \"问题\": \"...\"}。\n"
    "要求：不要合并不同事项；不要问额外的东西；不要给示例答案；一句话，不要寒暄。"
)

SYSTEM_ANSWER = (
    "你是环评报告编写助手。用户在回答一个具体问题，请从回答里抽取该字段的值，输出 JSON："
    "{\"值\": ..., \"没回答\": true/false}。\n"
    "铁律：只依据用户这句话；用户说不知道/没有/不清楚 → \"没回答\": true，值给 null；"
    "不要推断、不要补全。只输出 JSON。"
)

# ---------------------------------------------------------------- 工具

PUNCT = re.compile(r"[\s，。、；：！？,.;:!?（）()\[\]【】《》\"'“”‘’\-—~·]")


def _norm(s) -> str:
    """归一化：去空白与标点，便于"值是否出现在原话里"的字面比对。"""
    return PUNCT.sub("", str(s))


NUM_RX = re.compile(r"\d+(?:\.\d+)?")


def evidence_ok(value, text: str) -> tuple:
    """值能否在用户原话里找到依据。返回 (是否成立, 原因)。

    规则：字符串值 → 归一化后必须是原话的子串；数字 → 每个数字串都要在原话里出现；
    列表/字典 → 逐项递归。这条是对话侧的防编造闸门。
    """
    t = _norm(text)
    if t == "":
        return False, "用户这句话是空的"

    def walk(v, path=""):
        if isinstance(v, dict):
            for k, x in v.items():
                ok, why = walk(x, "%s.%s" % (path, k) if path else str(k))
                if not ok:
                    return ok, why
            return True, ""
        if isinstance(v, (list, tuple)):
            for i, x in enumerate(v):
                ok, why = walk(x, "%s[%d]" % (path, i))
                if not ok:
                    return ok, why
            return True, ""
        if isinstance(v, bool):
            return True, ""          # 布尔由下面的词表单独判
        if isinstance(v, (int, float)):
            vs = ("%g" % v)
            if vs in t:
                return True, ""
            # 允许用户写"1.2万""12000"这类等价写法：只要求数字串本身出现
            return (True, "") if vs in t else (False, "数字 %s 不在用户原话里" % vs)
        s = _norm(v)
        if s == "":
            return True, ""
        if s in t:
            return True, ""
        return False, "「%s」不在用户原话里" % str(v)[:40]

    return walk(value)


YES = ("是", "有", "需要", "会", "已经", "已", "属于", "true", "yes", "对")
NO = ("否", "没有", "无", "不会", "未", "不是", "不属于", "false", "no", "不需要")

# 否定线索（判"false"必须有其中一条）。
# 「还没/尚未/未开工」是口语里最常见的否定说法 —— 实测用户答「还没开工，正在办手续」，
# 因为词表里只有「没有」而被判"没有否定表述"拒掉。
NEG_CUES = ("不新增", "不外排", "不涉及", "不属于", "不直排", "不设", "不会", "不需要",
            "没有", "未涉及", "无涉及", "非直排", "不产生", "不排放", "未建设", "未开工",
            "不在", "不占", "不排", "不存", "否", "无",
            "还没", "尚未", "未曾", "没开工", "未开工", "不是", "未批", "没建")

# 2026-09-22 用户反馈（补答"废水排园区厂"后判据仍说"废水去向未抽到"）：
# 下面这些是**"不直排"的正面说法** —— 字面上不是否定词，但结论等价于否定。
# 原先一个都不认，于是"废水经预处理后纳管排入园区污水处理厂"这样的句子
# 既落不成 false、也过不了闸门，判据只能输出"废水去向未抽到，无法定论（缺事实）"。
#
# ⚠️ 只参与 **false 方向** 的判定，不参与"值为 true 时不得含否定线索"那一条 ——
# 否则"本项目废水不纳管、直接排放"里的"纳管"会把一个**真的直排**挡掉，
# 方向就反了（那是"少猜多拒"的反面：把该报的问题吞掉）。
EQUIV_NEG_CUES = ("纳管", "接管", "纳污水管", "进管网", "入管网", "排入园区",
                  "园区污水处理厂", "市政管网", "污水管网", "依托现有污水处理",
                  "送污水处理厂", "外送污水处理厂", "回用不外排", "全部回用",
                  "循环使用不外排")

# 枚举字段的常见缩写/口语说法（模型与用户都会这么写）。
# 只放"业界通用、不会歧义"的；拿不准的宁可丢弃（丢弃会进"未采信内容"，比填错好）。
ENUM_ALIAS = {"技改": "技术改造", "改技": "技术改造", "改扩建": "扩建",
              "技术改造项目": "技术改造", "异地新建": "新建"}


def _kw_tokens(name: str) -> list:
    """从字段中文名里抠出能代表"这件事"的词，用于判断所引片段是不是在说这件事。

    例：「新增工业废水直排」→ 工业废水 / 废水 / 直排。
    去掉的是"是否/有无/新增/情况"这类不含信息量的词。
    长词还要拆出所有 2 字滑动窗口 —— 实测：「是否开工建设」只留「开工建设」时，
    用户答「还没开工」会被判成"说的不是这件事"而误拒；拆出「开工」就对了。
    """
    s = re.sub(r"(是否|有无|有没有|新增|情况|的|了|为|是)", " ", str(name))
    toks = [t for t in re.split(r"[\s、，,（）()/]+", s) if len(t) >= 2]
    out = []
    for t in toks:
        out.append(t)
        if len(t) >= 4:                     # 长词再拆出后半段，如「工业废水直排」→「废水直排」
            out.append(t[-3:])
            out.append(t[-2:])
        for i in range(len(t) - 1):         # 所有 2 字滑动窗口
            out.append(t[i:i + 2])
    return out


def bool_ok(value: bool, quote: str, name: str) -> tuple:
    """布尔字段的证据核验。返回 (是否成立, 原因)。

    为什么单独做：布尔值没法用"值是否出现在原话里"来判断，所以之前**布尔字段完全绕过了闸门** ——
    实测模型拿「不新增河道取水」去填「新增工业废水直排=true」也照过，结果草稿里
    「废水直排」与用户说的「生产废水不外排」自相矛盾，自审直接报了一条**假的存在问题**。
    现在的两条规则：
      ① 所引片段必须真的在说这件事（含字段名里的关键词）；
      ② 值为 true 时片段不得含否定线索；值为 false 时必须有否定线索。
    """
    q = _norm(quote)
    if not q:
        return False, "布尔字段没有给出原文片段，不能凭推断填是非"
    toks = _kw_tokens(name)
    if toks and not any(t in q for t in toks):
        return False, "所引片段「%s」说的不是「%s」这件事" % (str(quote)[:30], name)
    neg = [w for w in NEG_CUES if _norm(w) in q]
    if value and neg:
        return False, "片段含否定（%s），不能填 true" % neg[0]
    if (not value) and not neg:
        # false 方向再认一类"正面说法的等价否定"（纳管/进管网/园区污水处理厂…），
        # 见 EQUIV_NEG_CUES 的注释：只在这里用，不参与上面的 true 方向。
        alt = [w for w in EQUIV_NEG_CUES if _cue_hit(q, w)]
        if not alt:
            return False, "片段里没有否定表述，不能填 false"
    return True, ""


def _cue_hit(q: str, w: str) -> bool:
    """q 里是否出现等价否定词 w —— **且它本身没被否定**。

    为什么要这一步：实测「本项目废水**不纳管**，经总排口直接排入厂外沟渠」这种句子，
    如果只做子串匹配，"纳管"命中 → 判成"非直排"→ 把一条**真的直排**吞掉，
    方向正好反了（比漏判更糟）。所以前面紧跟否定字的那次出现不算。
    """
    nw = _norm(w)
    if not nw:
        return False
    start = 0
    while True:
        i = q.find(nw, start)
        if i < 0:
            return False
        if i == 0 or q[i - 1] not in "不未无非没否别":
            return True
        start = i + 1


def normalize_bool(text: str):
    """把自由文本答案判成 true/false；判不出来返回 None（宁可不填）。"""
    t = _norm(text)
    if not t:
        return None
    for w in NO:
        if t.startswith(w) or ("不" + w[0] if len(w) == 1 else w) in t[:4]:
            return False
    for w in YES:
        if t.startswith(w):
            return True
    if "不" in t[:2]:
        return False
    return None


def normalize_enum(v, choices) -> str:
    """把自由文本归一到枚举值；归不了返回 ""（宁可不填）。

    2026-09-22 用户反馈（"这次是扩建""技改"直接搬原话）：
      枚举归一原先**只在"回答单个问题"这条路**上有（apply_answer），
      而"整段描述"那条路（parse_description）没有 enum 分支 ——
      模型返回"技改"会被原样存进事实表，随后 schema.validate() 判 error，
      `gen_routes` 直接 **status="rejected"、整份报告不生成**。
      两条写入口行为必须一致，所以抽成这一个函数共用。

    匹配顺序：原值 → 别名表（"技改"这类常见缩写）→ 双向子串 → 首尾字相同。
    最后一条是给"技改/技术改造"这种**缩写**用的：字符上互不包含，但首尾字一致。
    """
    if v in (None, "", []):
        return ""
    if choices and v in choices:
        return v
    nv = _norm(v)
    if not nv:
        return ""
    alias = ENUM_ALIAS.get(nv)
    if alias and (not choices or alias in choices):
        return alias
    for c in (choices or []):
        nc = _norm(c)
        if nc and (nc in nv or nv in nc):
            return c
    if len(nv) >= 2:
        for c in (choices or []):
            nc = _norm(c)
            if len(nc) >= 2 and nv[0] == nc[0] and nv[-1] == nc[-1]:
                return c
    return ""


def _cache(key: str, producer):
    os.makedirs(CACHE_DIR, exist_ok=True)
    p = os.path.join(CACHE_DIR, key + ".json")
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)["v"]
    v = producer()
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"v": v, "key": key, "PROMPT_VERSION": PROMPT_VERSION}, f,
                  ensure_ascii=False, indent=1)
    return v


def _key(*parts) -> str:
    """缓存键 = 版本 + 提示词原文 + 输入。

    提示词必须进键：本轮踩过两次 —— ① 改了 SYSTEM 提示词却没升版本号，命中了旧缓存；
    ② 改了**拼给模型的 user 消息模板**（字段清单格式），键还是老样子，同样命中旧缓存，
    新格式根本没跑。所以现在一律用 `_model_json_cached`：键由 (system, user, max_tokens)
    直接算出，调用点不可能再忘。
    """
    return hashlib.sha1(json.dumps([PROMPT_VERSION] + list(parts),
                                   ensure_ascii=False).encode("utf-8")).hexdigest()


def _model_json_cached(system: str, user: str, max_tokens: int = 1200):
    """带缓存的模型 JSON 调用。缓存键覆盖 system+user+max_tokens。"""
    return _cache(_key(system, user, max_tokens),
                  lambda: _model_json(system, user, max_tokens))


def _model_json(system: str, user: str, max_tokens: int = 1200):
    from audit.llm import call_model
    txt = call_model([{"role": "system", "content": system},
                      {"role": "user", "content": user}],
                     max_tokens=max_tokens, temperature=0.0) or ""
    txt = txt.strip()
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\n?|```$", "", txt).strip()
    m = re.search(r"[\{\[].*[\}\]]", txt, re.S)
    if not m:
        raise ValueError("模型没给出 JSON：%s" % txt[:120])
    return json.loads(m.group(0))


# ---------------------------------------------------------------- 字段清单（给模型看）

def _field_menu(groups=("填报", "判定输入")) -> str:
    """给模型的字段清单。用 **JSON** 给，不用「key（中文名）」这种行文本 ——
    本轮实测：行文本会让模型把「建设地点（建设地点）」整串当成 key，10 个字段全丢。
    """
    rows = []
    for f in schema.FIELDS:
        if f.source not in groups:
            continue
        rows.append({"key": f.key, "中文名": f.name,
                     "类型": {"str": "文本", "float": "数字", "int": "整数",
                              "bool": "true/false", "list": "数组", "enum": "枚举"}[f.type],
                     "说明": (("可选值：" + "/".join(f.choices)) if f.choices else f.note),
                     "单位": f.unit})
    return json.dumps(rows, ensure_ascii=False, indent=1)


def _match_key(k: str, ks: dict):
    """把模型给的 key 归一成真实字段名。容忍「key（中文名）」「中文名」「带空格」等漂移。

    注意括号可能是**嵌套**的（`用地面积_m2（用地（用海）面积）`），非贪婪正则会切错位置，
    所以从第一个左括号切到最后一个右括号。
    """
    k = str(k).strip()
    if k in ks:
        return k
    base = re.sub(r"[（(].*[)）]\s*$", "", k).strip()
    if base in ks:
        return base
    for f in schema.FIELDS:                    # 按中文名反查
        if k == f.name or base == f.name:
            return f.key
    for f in schema.FIELDS:                    # 中文名互相包含（如「用地（用海）面积」）
        if f.name and (f.name in k or k in f.name):
            return f.key
    return None


# ---------------------------------------------------------------- ① 抽取

def _quote_ok(quote: str, text: str) -> bool:
    """片段是否真的逐字出现在用户原话里（去空白标点后比对）。"""
    q = _norm(quote)
    return bool(q) and len(q) >= 2 and q in _norm(text)


def _subseq_ok(v, text: str) -> bool:
    """值的字符是否按顺序出现在文本里（宽松版"有依据"）。

    用于列表项：容忍模型把「布袋除尘和双碱法脱硫」整理成「布袋除尘+双碱法脱硫」，
    但凭空造的词（如「编造的小学」）过不了 —— 那些字在用户原话里根本不存在。
    """
    s, t = _norm(v), _norm(text)
    if not s:
        return True
    it = iter(t)
    return all(ch in it for ch in s)


def _filter_value(v, text: str, quote: str = "", fname: str = "") -> tuple:
    """按证据过滤一个值。返回 (保留的值, 说明列表)。

    两条证据规则：
      · `原文` 片段必须逐字出现在用户原话里（这是主要判据 —— 允许模型把值整理成
        规范写法，但依据必须是真的；实测过：模型把「布袋除尘和双碱法脱硫」写成
        「布袋除尘+双碱法脱硫」，纯字面比对会误杀，所以以片段为准）；
      · 值里的数字必须出现在片段里（防止片段真、数字假）。
    列表则**逐项过滤**，只删没依据的那部分。
    """
    notes = []
    if not quote:
        # **没有片段不等于免检**（本轮真踩过：模型返回旧格式、片段为空，闸门被整段绕过，
        # 编造的"项目名称"直接过关）。没有片段就退回最严的字面比对。
        ok, why = evidence_ok(v, text)
        if not ok:
            return None, ["未给出原文片段，且值在用户描述里找不到依据：%s" % why]
        notes.append("未给出原文片段，已按字面比对通过")
        return v, notes
    if not _quote_ok(quote, text):
        return None, ["给出的原文片段在用户描述里找不到：「%s」" % str(quote)[:40]]
    # 标量字段：**值本身**必须出现在片段里（片段只是定位）。
    # 为什么：本轮实测模型给 项目名称="生物质锅炉项目"，片段是真的（用户说"建一台…生物质锅炉"），
    # 但"生物质锅炉项目"这个名字是模型自己攒的 —— 报告标题上编个项目名不能接受。
    # 列表型字段（设备/措施/保护目标）允许整理成结构化写法，按片段+数字把关。
    if isinstance(v, bool):
        ok, why = bool_ok(v, quote, fname)
        return (v, []) if ok else (None, [why])
    if not isinstance(v, list):
        ok, why = evidence_ok(v, quote)
        if not ok:
            return None, ["值不在所引片段里：%s" % why]

    def nums_ok(val) -> tuple:
        if not quote:
            return True, ""
        qn = _norm(quote)
        for n in NUM_RX.findall(json.dumps(val, ensure_ascii=False)):
            # 数字按**等价写法**比对：值 3000.0 与用户写的 3000 是一回事
            # （本轮误杀过：float 序列化成 "3000.0"，片段里是 "3000"）
            forms = {n}
            try:
                fv = float(n)
                forms.add("%g" % fv)
                if fv == int(fv):
                    forms.add(str(int(fv)))
            except ValueError:
                pass
            if not any(fm in qn for fm in forms):
                return False, "数字 %s 不在所引片段里" % n
        return True, ""

    if isinstance(v, list):
        kept = []
        for i, item in enumerate(v):
            if isinstance(item, dict):
                ok, why = nums_ok(item)
                good = dict(item) if ok else {}
                if not ok:
                    notes.append("第%d项%s" % (i + 1, why))
                # 文字内容也要能追溯到用户原话（本轮补：之前只校验了数字，
                # 结果编造的「编造的小学」照样进了环境保护目标）
                for k, x in list(good.items()):
                    if isinstance(x, str) and x.strip():
                        if not (_norm(x) in _norm(quote) or _subseq_ok(x, quote or text)):
                            good.pop(k)
                            notes.append("第%d项「%s」无依据已删" % (i + 1, x[:20]))
                if good:
                    kept.append(good)
                else:
                    notes.append("第%d项整条无依据已删" % (i + 1))
            else:
                if not (_norm(item) in _norm(quote) or _subseq_ok(item, quote or text)):
                    notes.append("第%d项无依据已删" % (i + 1))
                    continue
                kept.append(item)
        return kept, notes
    ok, why = nums_ok(v)
    return (v, notes) if ok else (None, [why])


def parse_description(text: str) -> dict:
    """用户描述 → {采纳: {字段:值}, 丢弃: [{字段,值,原因}], 依据: {字段:原文片段}}。"""
    ks = schema.by_key()
    user = ("字段清单（JSON 数组；输出的 key 必须与清单里的 key 完全一致）:\n%s\n\n"
            "用户的项目描述：\n%s\n\n"
            "请输出 JSON：{\"字段key\": {\"值\": 值, \"原文\": \"逐字复制的片段\"}, ...}\n"
            "**每个字段都必须给「原文」**（包括列表型字段）；没有原文的字段视为没有依据。"
            "只含用户明确说过的字段。" % (_field_menu(), text))
    raw = _model_json_cached(SYSTEM_EXTRACT, user, 2000)
    if not isinstance(raw, dict):
        return {"采纳": {}, "丢弃": [{"字段": "-", "值": str(raw)[:60], "原因": "模型没给对象"}],
                "依据": {}}
    keep, drop = {}, []
    keep_ev = {}
    for k0, box in raw.items():
        k = _match_key(k0, ks)
        if not k:
            drop.append({"字段": str(k0)[:40], "值": str(box)[:60], "原因": "不是已定义字段"})
            continue
        if k in keep:
            continue
        f = ks[k]
        # 兼容两种输出：带 {"值","原文"} 的规范格式，或直接给值（老格式）
        if isinstance(box, dict) and ("值" in box or "原文" in box):
            v, quote = box.get("值"), str(box.get("原文") or "")
        else:
            v, quote = box, ""
        if v in (None, "", []):
            continue
        if f.type == "bool":
            if isinstance(v, bool):
                b = v
            else:
                b = normalize_bool(str(v))
            if b is None:
                drop.append({"字段": k, "值": str(v)[:60], "原因": "是非题判不出来"})
                continue
            v = b
        elif f.type in ("float", "int"):
            try:
                v = float(v) if f.type == "float" else int(float(v))
            except Exception:                                     # noqa: BLE001
                drop.append({"字段": k, "值": str(v)[:60], "原因": "不是数字"})
                continue
        elif f.type == "list" and not isinstance(v, list):
            v = [v]
        elif f.type == "enum":
            # 2026-09-22：枚举字段必须在这里归一，否则原话（"这次是扩建"）会一路走到
            # schema.validate() 报 error → gen_routes 判"校验未通过" → 整份报告不生成。
            ev = normalize_enum(v, getattr(f, "choices", None))
            if not ev:
                drop.append({"字段": k, "值": str(v)[:60],
                             "原因": "只能是 %s" % "/".join(getattr(f, "choices", None) or [])})
                continue
            v = ev
        elif f.type == "str" and not isinstance(v, str):
            v = str(v)
        # **出处核验**：逐项过滤 —— 有依据的留下，没依据的删掉并说明
        kept, notes = _filter_value(v, text, quote, f.name)
        if kept in (None, "", []):
            drop.append({"字段": k, "值": json.dumps(v, ensure_ascii=False)[:60],
                         "原因": "；".join(notes) or "无依据"})
            continue
        if notes:
            drop.append({"字段": k, "值": json.dumps(kept, ensure_ascii=False)[:60],
                         "原因": "部分保留：" + "；".join(notes)})
        keep[k] = kept
        keep_ev[k] = quote
    return {"采纳": keep, "丢弃": drop, "依据": keep_ev}


# ---------------------------------------------------------------- ② 缺口 → ③ 提问

# 该先问的字段（越靠前越先问）。理由：项目名称是报告封面的门面；
# 建设项目行业类别直接决定名录档级；行业类别/坐标是表一的骨架。
FIRST_ASK = [
    "项目名称", "建设项目行业类别", "国民经济行业类别", "建设地点", "地理坐标",
    "建设性质", "是否开工建设", "总投资_万元", "环保投资_万元", "用地面积_m2",
    "主要原辅材料", "主要生产设备", "产品及产能", "工艺流程和产排污环节",
    "废气污染物清单", "危险物质清单", "环境保护目标", "水平衡说明",
]


def gaps(data: dict, max_ask: int = 6) -> dict:
    """哪些还没问到、为什么问。**代码决定**，模型只负责措辞。"""
    ks = schema.by_key()
    v = schema.validate(data, strict=False)
    missing_keys = [x.split("（")[0] for x in v["missing_required"]]
    items, seen = [], set()

    def add(key, why, prio):
        if key in seen or (data.get(key) not in (None, "", [])):
            return
        seen.add(key)
        f = ks.get(key)
        items.append({"key": key, "中文名": (f.name if f else key), "为什么问": why,
                      "类型": (f.type if f else "str"), "优先级": prio})

    # 1) 名录档级/专项评价必须的判定输入 —— 先问这些，因为它们直接决定结论
    from gen import decide as _decide
    try:
        cat = _decide.decide(data)
        for x in (cat["名录"].get("待补事实") or []):
            items.append({"key": "补充事实", "中文名": "补充事实：" + x, "为什么问":
                          "名录档级靠这条条件比对（照原文回答即可）", "类型": "补充事实",
                          "事实名": x, "优先级": 1})
        for r in cat["专项评价"]["要素"]:
            if r.get("status") == "unknown":
                items.append({"key": "专项用事实_" + r["element"], "中文名": r["element"] + "专项评价的判定输入",
                              "为什么问": r.get("reason") or "", "类型": "bool", "优先级": 2})
    except Exception:                                            # noqa: BLE001
        pass
    # 2) 必填缺项：表一基本信息的先问
    for k in missing_keys:
        f = ks.get(k)
        if not f:
            continue
        prio = 3 if f.group in ("表一",) else 5
        add(k, f.note or "报告表必填项", prio)
    # 3) 挑哪些来问：**不能全被判定类占满** ——
    #    本轮实测：严格按优先级排，6 个名额全被名录/专项的判定输入吃掉，
    #    连"项目名称"都没问到。所以按桶轮流取：判定关键的最多 2 条，其余给基本信息。
    # 4) 同一桶内按"该先问什么"排：项目身份与名录输入排前面，
    #    否则按 key 的码位排会把「项目名称」挤到第二轮（实测踩到）。
    buckets = {1: [], 2: [], 3: [], 5: []}
    for it in items:
        buckets.setdefault(it["优先级"], []).append(it)
    for b in buckets.values():
        b.sort(key=lambda x: (FIRST_ASK.index(x["key"]) if x["key"] in FIRST_ASK else 999,
                              x["key"]))
    picked, quota = [], {1: 1, 2: 1, 3: max(0, max_ask - 2), 5: 0}
    for p in (1, 2, 3):
        picked.extend(buckets.get(p, [])[:quota[p]])
    if len(picked) < max_ask:                     # 还有名额就从 5 类补
        picked.extend(buckets.get(5, [])[:max_ask - len(picked)])
    rest = [x for x in items if x not in picked]
    return {"要问": picked, "还剩": len(rest), "缺项总数": len(items),
            "剩余项": [x["中文名"] for x in rest[:12]]}


def phrase_questions(items: list) -> list:
    """把待问事项说成人话（模型措辞，缓存；失败则退回模板措辞）。"""
    if not items:
        return []
    plain = [{"key": it["key"], "字段名": it["中文名"], "说明": it["为什么问"]} for it in items]
    user = ("需要确认的事项：\n%s\n\n请输出 JSON 数组，每项 {\"key\": 字段名, \"问题\": \"...\"}"
            % json.dumps(plain, ensure_ascii=False, indent=1))
    try:
        got = _model_json_cached(SYSTEM_ASK, user, 900)
        got = got if isinstance(got, list) else []
        by = {str(x.get("key")): str(x.get("问题") or "") for x in got if isinstance(x, dict)}
    except Exception:                                            # noqa: BLE001
        by = {}
    out = []
    for it in items:
        q = by.get(it["key"]) or ("请补充：%s（%s）" % (it["中文名"], it["为什么问"]))
        out.append({"key": it["key"], "问题": q, "为什么问": it["为什么问"],
                    "中文名": it["中文名"], "类型": it["类型"],
                    "可选值": it.get("可选值") or [], "事实名": it.get("事实名")})
    return out


# ---------------------------------------------------------------- ④ 回答 → 落库

def apply_answer(data: dict, item: dict, answer: str) -> dict:
    """把用户对一个问题的自由文本回答落进 data。返回 {data, 采纳, 说明}。"""
    key, text = item.get("key"), (answer or "").strip()
    if not text or _norm(text) in ("不知道", "不清楚", "没有", "无", "跳过", "skip", "没有相关信息"):
        return {"data": data, "采纳": False, "说明": "用户未提供（不猜）"}
    ks = schema.by_key()

    # 「补充事实」类：用户回答的就是名录条件对应的值
    if key == "补充事实" or key.startswith("专项用事实_"):
        name = item.get("事实名") or item.get("中文名", "").replace("补充事实：", "")
        b = normalize_bool(text)
        sup = list(data.get("补充事实") or [])
        if item.get("类型") == "bool" or b is not None and not NUM_RX.search(text):
            sup.append({"名称": name, "不适用": b is False} if b is not None
                       else {"名称": name, "值": text})
        else:
            nums = NUM_RX.findall(text)
            sup.append({"名称": name, "值": (float(nums[0]) if nums else text),
                        "单位": ("吨/小时" if "吨" in text and "小时" in text else "")})
        d = dict(data)
        d["补充事实"] = sup
        return {"data": d, "采纳": True, "说明": "已记为补充事实「%s」" % name}

    f = ks.get(key)
    if not f:
        return {"data": data, "采纳": False, "说明": "未知字段 %s" % key}

    user = ("字段：%s（%s），类型 %s，说明：%s\n用户的回答：%s\n\n输出 {\"值\": ..., \"没回答\": false}"
            % (key, f.name, f.type, f.note or "", text))
    try:
        got = _model_json_cached(SYSTEM_ANSWER, user, 600)
    except Exception as exc:                                     # noqa: BLE001
        return {"data": data, "采纳": False, "说明": "解析回答失败：%s" % exc}
    if not isinstance(got, dict) or got.get("没回答"):
        return {"data": data, "采纳": False, "说明": "回答里没有这一项（不猜）"}
    v = got.get("值")
    if v in (None, "", []):
        return {"data": data, "采纳": False, "说明": "没抽到值"}
    if f.type == "bool":
        b = v if isinstance(v, bool) else normalize_bool(str(v))
        if b is None:
            return {"data": data, "采纳": False, "说明": "是非题判不出来"}
        v = b
    elif f.type in ("float", "int"):
        try:
            v = float(v) if f.type == "float" else int(float(v))
        except Exception:                                        # noqa: BLE001
            return {"data": data, "采纳": False, "说明": "不是数字"}
    elif f.type == "list" and not isinstance(v, list):
        v = [v]
    elif f.type == "enum" and f.choices and v not in f.choices:
        ev = normalize_enum(v, f.choices)
        if not ev:
            return {"data": data, "采纳": False, "说明": "只能是 %s" % "/".join(f.choices)}
        v = ev
    if f.type == "bool":
        ok, why = bool_ok(bool(v), text, f.name)
        if not ok:
            return {"data": data, "采纳": False, "说明": "是非题不能这么答：%s" % why}
        d = dict(data)
        d[key] = bool(v)
        return {"data": d, "采纳": True,
                "说明": "已记录 %s＝%s" % (f.name, "是" if v else "否")}
    ok, why = evidence_ok(v, text)
    if not ok:
        return {"data": data, "采纳": False, "说明": "回答里找不到依据：%s" % why}
    d = dict(data)
    d[key] = v
    return {"data": d, "采纳": True, "说明": "已记录 %s＝%s" % (f.name, json.dumps(v, ensure_ascii=False)[:40])}


def summarize(data: dict) -> dict:
    """当前已知事实概览（给页面显示"我目前了解到什么"）。"""
    rows = []
    for f in schema.FIELDS:
        v = data.get(f.key)
        if v in (None, "", []):
            continue
        rows.append({"字段": f.name, "值": v if isinstance(v, (str, int, float, bool)) else
                     json.dumps(v, ensure_ascii=False)[:60]})
    for t in (data.get("补充事实") or []):
        rows.append({"字段": "补充事实：" + str(t.get("名称")),
                     "值": ("不适用" if t.get("不适用") else t.get("值"))})
    return {"已知事实": rows, "已填字段数": len(rows)}