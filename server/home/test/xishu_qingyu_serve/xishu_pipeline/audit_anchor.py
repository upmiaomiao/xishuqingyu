#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核意见 → 报告原文的锚定层（批注视图与批注版 PDF **共用同一份判定**）。

为什么单独抽一层：
  · 「在线批注视图」要的是 *字符区间*（在网页文本里画高亮），
    「批注版 PDF」要的是 *坐标矩形*（在 PDF 里画高亮批注）；
  · 两者的"这一条到底锚在哪"必须是同一个答案，否则用户在线看到的和
    导出的 PDF 里标的不是一回事 —— 这类不一致比不精确更伤信任。

三档定位（用户 2026-09-22 拍板：接受降级，但**必须把档位标出来**）：

  ① 精确  摘录与原文逐字一致（允许页码内换行造成的空白差异）
  ② 近似  按关键词或表格定位：模型给的"摘录"相当一部分不是原文句子
          （实测样例：「封面出现『环境影响报告书』」「章节定位：项目概况」），
          还有表格被压成一行（「1 | CO | 随烟气排放 | — | 7.5 | —」）
  ③ 仅页码 正文里找不到，只保证"这条意见属于第 N 页"，绝不假装高亮对了地方

实测基线（6 份报告 89 条证据）：精确约 25~40%。**这个数字不美化**，
所以档位要显示给用户，导出物里也要留痕。
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

AUDIT_HOME = os.environ.get("AUDIT_HOME", "/data/eia_audit")
if AUDIT_HOME not in sys.path:
    sys.path.insert(0, AUDIT_HOME)

RESULT_DIR = os.path.join(AUDIT_HOME, "_审核结果")

LEVEL_EXACT = "精确"
LEVEL_NEAR = "近似"
LEVEL_PAGE = "仅页码"
# 「无证据」单独一档：不适用项本来就不给证据（一份报告 18 项里通常 9 项如此）。
# 第一版把它混进「仅页码」，统计出来 74 条"定位失败"里其实大半是**设计如此** ——
# 把设计如此说成失败，是自欺，也会让用户以为定位能力很差。
LEVEL_NONE = "无证据"
LEVELS = (LEVEL_EXACT, LEVEL_NEAR, LEVEL_PAGE, LEVEL_NONE)

# 页码是 PDF 物理页；报告正文里印的是印刷页号，两者会差一个封面/目录的偏移。
# 审核意见里的「-P19」用的是**印刷页号**（parse.py 的注释已说明），
# 批注里两个都显示，避免用户照着印刷页号去 PDF 里翻却翻错。
_WS = re.compile(r"[\s\u3000]+")
_PUNCT = re.compile(r"[\s\u3000|｜·・,，。；;：:、（）()\[\]【】{}<>《》\"'`~!！?？—\-–_/\\]+")
_SEG = re.compile(r"[\u4e00-\u9fff0-9A-Za-z]{4,}")


def _norm(s: str) -> str:
    """折空白：PDF 抽出来的正文在一句话中间会有换行，摘录里没有。"""
    return _WS.sub("", s or "")


def _squeeze(s: str) -> str:
    """再折标点：只剩中日韩文字与字母数字，用于"近似"档。"""
    return _PUNCT.sub("", s or "")


def find_span(text: str, quote: str):
    """在 text 里找 quote，允许字符之间出现任意空白。返回 (start, end) 或 None。"""
    q = _norm(quote)
    if len(q) < 2 or not text:
        return None
    # 逐字符 \s* 连接：既容忍换行，也容忍 PDF 抽出来的字间空格
    pat = r"\s*".join(re.escape(c) for c in q)
    m = re.search(pat, text)
    if m:
        return (m.start(), m.end())
    # 有的摘录带引号（「封面出现『环境影响报告书』」里的书名号是模型加的），
    # 去掉首尾引号再试一次
    q2 = q.strip("「」『』\"'《》")
    if q2 and q2 != q:
        pat = r"\s*".join(re.escape(c) for c in q2)
        m = re.search(pat, text)
        if m:
            return (m.start(), m.end())
    return None


def _cells_of(quote: str) -> list:
    """把表格行拆成有意义的单元格。

    两种形态都要认：
      · 「1 | CO | 随烟气排放 | — | 7.5 | —」（md 表格行，竖线分隔）
      · 「序号    敏感点名称      相对厂址方位」（PDF 抽出来的表头，靠 2 个以上空格分列）
    """
    raw = re.split(r"[|｜\t]|\s{2,}", quote or "")
    out = []
    for c in raw:
        c = _WS.sub(" ", c).strip()
        if not c or c in ("—", "-", "－", "/", "无"):
            continue
        out.append(c)
    return out


def _keywords(quote: str, min_len: int = 4) -> list:
    """摘录里最像原文的片段，长的优先（近似档用）。

    纯数字段要排到最后：实测「序号 环保目标名称 坐标 …」这条摘录里的
    `437296226` 会被当成关键词命中，高亮落在表格里的一个坐标数字上 ——
    标错了地方比不标更糟。有汉字的片段才是像原文的东西。
    """
    segs = [s for s in _SEG.findall(quote or "") if len(s) >= min_len]
    segs.sort(key=lambda s: (bool(re.search(r"[\u4e00-\u9fff]", s)), len(s)), reverse=True)
    body = _squeeze(quote)
    if len(body) >= min_len:
        segs.append(body)
    return segs


def _match_table(page_tables: list, cells: list):
    """表格定位：该页有没有一张表同时装着这些单元格。返回表序号或 None。"""
    if len(cells) < 3 or not page_tables:
        return None
    need = [_norm(c) for c in cells if len(_norm(c)) >= 2]
    if len(need) < 2:
        return None
    for ti, tb in enumerate(page_tables):
        flat = [_norm("".join(str(c) for c in row)) for row in (tb.get("rows") or [])]
        hit = sum(1 for c in need if any(c in f for f in flat))
        if hit >= len(need):
            return ti
    return None


def locate(parsed: dict, page: int, quote: str) -> dict:
    """给一条证据定位。返回 {"level","span","table","hit","why"}。

    `hit` 是**这次真正匹配上的原文片段**，和 `quote` 不是一回事：
      · 精确档   hit == quote（逐字命中）；
      · 近似档   hit 是命中的那个关键词/表名，quote 往往整条都不在版面里；
      · 仅页码   hit 为空。
    为什么要单独留它：PDF 批注要"框住命中的那几个字"。只拿 quote 去搜，
    近似档一条都框不出来（实测 54 条里 0 条），最后只能整份报告都不画高亮。
    """
    texts = parsed.get("page_text") or []
    if not page or page < 1 or page > len(texts):
        return {"level": LEVEL_PAGE, "span": None, "table": None, "hit": "",
                "why": "证据页码超出报告范围"}
    text = texts[page - 1]
    if not (text or "").strip():
        return {"level": LEVEL_PAGE, "span": None, "table": None, "hit": "",
                "why": "该页没有文本层（扫描页），只能按页码核对"}

    sp = find_span(text, quote)
    if sp:
        return {"level": LEVEL_EXACT, "span": [sp[0], sp[1]], "table": None,
                "hit": text[sp[0]:sp[1]],
                "why": "与原文逐字一致"}

    page_tables = _page_tables(parsed, page)
    cells = _cells_of(quote)
    ti = _match_table(page_tables, cells)
    if ti is not None:
        return {"level": LEVEL_NEAR, "span": None, "table": ti,
                "hit": "".join(cells[:3]),
                "why": "按表格内容定位到本页第 %d 张表" % (ti + 1)}

    for kw in _keywords(quote):
        sp = find_span(text, kw)
        if sp:
            return {"level": LEVEL_NEAR, "span": [sp[0], sp[1]], "table": None,
                    "hit": text[sp[0]:sp[1]],
                    "why": "按关键词「%s」定位，可能有偏移" % kw[:16]}
    return {"level": LEVEL_PAGE, "span": None, "table": None, "hit": "",
            "why": "正文里找不到该摘录（多为复核结论性描述），请核对本页"}


_TABLE_IDX: dict = {}
_TABLE_LOCK = threading.Lock()


def _page_tables(parsed: dict, page: int) -> list:
    """页 → 该页表格列表（按 sha1 缓存页索引，不按 id()：id 会被回收复用）。"""
    key = str(parsed.get("sha1") or "") + "|" + str(len(parsed.get("tables") or []))
    with _TABLE_LOCK:
        idx = _TABLE_IDX.get(key)
        if idx is None:
            by_page: dict = {}
            for t in parsed.get("tables") or []:
                by_page.setdefault(int(t.get("page") or 0), []).append(t)
            if len(_TABLE_IDX) >= 3:          # 只留最近几份，别把整库攒在内存里
                _TABLE_IDX.clear()
            _TABLE_IDX[key] = by_page
            idx = by_page
        return idx.get(page, [])


# ------------------------------------------------------------------ 结果文件

def load_result(name: str) -> dict:
    path = os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json")
    if not os.path.isfile(path):
        raise FileNotFoundError("还没有该报告的审核结果，请先运行审核")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_parsed(name: str, pdf_path: str, allow_parse: bool = True):
    """取解析缓存（_cache/<sha1>.json）。缺失时按需解析一次。"""
    from audit.parse import load_or_parse, sha1_of          # noqa: E402
    from audit.runner import cache_dir                       # noqa: E402
    cdir = cache_dir()
    cp = os.path.join(cdir, sha1_of(pdf_path) + ".json")
    if not os.path.isfile(cp) and not allow_parse:
        raise FileNotFoundError("该报告还没有解析缓存")
    rep = load_or_parse(pdf_path, cache_dir=cdir)
    return rep.to_json()


def build_anchors(result: dict, parsed: dict) -> list:
    """把审核结果摊平成"可锚定的批注"列表。"""
    out = []
    labels = parsed.get("page_labels") or {}
    for i, it in enumerate(result.get("items") or [], 1):
        evs = it.get("证据") or []
        if not evs:
            out.append({
                "item": i, "审核项": it.get("审核项") or "", "类别": it.get("类别") or "",
                "结论": it.get("AI审核") or "", "适用": bool(it.get("适用")),
                "置信度": it.get("置信度") or "", "参考依据": it.get("参考依据") or "",
                "理由": it.get("理由") or "", "需人工确认": it.get("需人工确认") or [],
                "page": None, "printed": None, "环评文件": it.get("环评文件") or "",
                "quote": "", "来源": "",
                "level": LEVEL_NONE, "span": None, "table": None, "hit": "",
                # 措辞要中性：没有证据的**不只是**不适用项，也可能是因为没抽到资料而存疑，
                # 写成"多为不适用项"会让审核人把「疑似」条目误当成「不涉及」略过。
                "why": "该审核项没有给出证据，需人工核对；不代表没有问题",
            })
            continue
        for e in evs:
            page = e.get("page")
            page = int(page) if isinstance(page, (int, float)) and page else None
            quote = str(e.get("quote") or "")
            loc = locate(parsed, page or 0, quote)
            out.append({
                "item": i, "审核项": it.get("审核项") or "", "类别": it.get("类别") or "",
                "结论": it.get("AI审核") or "", "适用": bool(it.get("适用")),
                "置信度": it.get("置信度") or "", "参考依据": it.get("参考依据") or "",
                "理由": it.get("理由") or "", "需人工确认": it.get("需人工确认") or [],
                "page": page, "printed": labels.get(str(page)) if page else None,
                "环评文件": it.get("环评文件") or "",
                "quote": quote, "来源": str(e.get("source") or ""),
                "level": loc["level"], "span": loc["span"], "table": loc["table"],
                "hit": loc.get("hit") or "", "why": loc["why"],
            })
    return out


def annot_stats(anchors: list) -> dict:
    """按定位档位统计。**有证据的批注**才参与定位率分母，
    没有证据的（不适用项）单列一档，不冒充"定位失败"。"""
    st = {lv: 0 for lv in LEVELS}
    for a in anchors:
        lv = a.get("level") or LEVEL_PAGE
        st[lv] = st.get(lv, 0) + 1
    st["合计"] = len(anchors)
    st["有证据"] = st[LEVEL_EXACT] + st[LEVEL_NEAR] + st[LEVEL_PAGE]
    return st


def page_payload(parsed: dict, page: int) -> dict:
    texts = parsed.get("page_text") or []
    labels = parsed.get("page_labels") or {}
    marks = parsed.get("page_marks") or {}
    empty = set(parsed.get("empty_pages") or [])
    page = max(1, min(int(page), len(texts) or 1))
    return {
        "n": page,
        "printed": labels.get(str(page)),
        "mark": marks.get(str(page)),
        "empty": (page in empty) or not (texts[page - 1] or "").strip(),
        "text": texts[page - 1] if texts else "",
        "tables": _page_tables(parsed, page),
        "total": len(texts),
    }
