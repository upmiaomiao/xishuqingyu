#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""模型兜底抽取：语义型问题交给模型，但**必须交出可回溯的原文**。

为什么不用纯正则：语义型问题（"本项目废水是否直排"）正则一定会假阳性，
本项目已实测到两条 ——
  · 玻璃报告表："取水口（潦河）"其实出自规划环评里**别的**供水公司取水口 → 误判"新增河道取水"
  · 邵武报告书：原文是"施工废水**未**直接排入周边地表水体" → 误判"废水直排"
中文否定词跨字，正则的负向断言不可靠。

所以：模型答题 → 代码机械核验（原文必须能在它自称的那一页里检索到）→
核验不过一律留空（判据层会把它降级为"存在疑似问题"，绝不猜）。
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request

MODEL_URL = os.environ.get("AUDIT_MODEL_URL", "http://10.201.31.12:8000/v1/chat/completions")
MODEL_NAME = os.environ.get("AUDIT_MODEL_NAME", "xishu-qingyu-v5")

SYSTEM = (
    "你是环评报告审核助手。只依据我给你的页面原文回答，不得使用任何外部知识、不得推测。"
    "输出必须严格是三行，每行一个字段，不要写任何其他内容：\n"
    "结论：是 / 否 / 不确定\n"
    "页码：原文所在的 PDF 物理页页码（整数；不确定时写 不确定）\n"
    "定位短语：从该页原文中**逐字复制**的 10~20 字连续片段，用来定位依据（不确定时留空）\n"
    "注意：定位短语必须是原文里真实存在的字，不能改写、不能压缩、不能拼接不同段落。"
    "宁可写「结论：不确定、定位短语留空」，也不要猜。"
)


def call_model(messages: list, max_tokens: int = 1024, temperature: float = 0.0,
               timeout: int = 300, thinking: bool = False) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": thinking},
        "stream": False,
    }
    req = urllib.request.Request(
        MODEL_URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


def parse_reply(text: str) -> dict:
    """解析模型的固定格式答复（结论 / 页码 / 定位短语）。

    实测 xishu-qingyu-v5 的行为：给了原文就会自然作答，强行要 JSON 会整段失效；
    照三行格式能答对，但**常常省标签**、且常把三个字段挤在一行用「；」分隔
    （实测输出：「否；13；用水由市政管网提供…」）。因此解析必须同时容忍
    换行与分号分隔，并按"像结论 / 像页码 / 其余"分类，不能只按行切。
    """
    t = (text or "").strip()
    j = parse_json(t)
    if j and ("value" in j or "found" in j):
        return {"value": j.get("value", j.get("found")), "page": j.get("page"),
                "anchor": j.get("quote") or j.get("anchor") or "",
                "reason": j.get("reason") or "", "parsed_by": "json"}

    def grab(label):
        m = re.search(rf"{label}\s*[:：]\s*([^\n；;]+)", t)
        return m.group(1).strip() if m else None

    concl, page, anchor = grab("结论"), grab("页码"), grab("定位短语") or grab("原文摘录")
    parsed_by = "labels"
    if concl is None or anchor is None:
        parsed_by = "split"
        pieces = [p.strip() for p in re.split(r"[\n；;]+", t) if p.strip()]
        for p in pieces:
            if concl is None and re.match(r"^(是|否|不确定|无法确定|不能确定|未提及|无)", p) \
                    and len(p) <= 30:
                concl = p
            elif re.fullmatch(r"\d{1,4}", p) and page is None:
                page = p
        rest = [p for p in pieces if p is not concl and p != page and not re.fullmatch(r"\d{1,4}", p)]
        if rest:
            anchor = max(rest, key=len)
        if concl is None and pieces:
            concl = pieces[0]
    if concl is None:
        return {"value": None, "page": None, "anchor": "", "reason": "",
                "parsed_by": "fail", "_raw": t}
    anchor = re.sub(r"^\s*[:：]?\s*", "", anchor or "").strip()
    pg = None
    if page:
        m = re.search(r"(\d{1,4})", page)
        pg = int(m.group(1)) if m else None
    if re.search(r"不确定|无法确定|不能确定", concl):
        val = None
    elif re.match(r"^(是|属于)", concl) or ("属于" in concl[:6] and "不属于" not in concl[:8]):
        val = True
    elif re.match(r"^(否|不是)", concl) or "不属于" in concl[:8]:
        val = False
    else:
        val = None
    return {"value": val, "page": pg, "anchor": anchor, "reason": concl,
            "parsed_by": parsed_by}


def match_fragment(rep, page, anchor, min_len: int = 6) -> str:
    """从模型给的定位短语里，找出**真正存在于该页**的最长片段。

    为什么要这样：模型很爱把事实卡片里的整行抄下来，而卡片是代码拼的
    （「名录条目：十九、…」「行业类别（分类管理名录） | 十九、…」这类合成前缀
    在页面上并不存在），整串核验必然失败 —— 但其中的某一格文本是真实存在的。
    于是取最长可核验片段：既拦住真正编造的（一个片段都找不到），
    又不会因为模型多抄了个前缀就丢掉正确答案。
    """
    if not page:
        return ""
    try:
        txt = norm(rep.page_text[page - 1])
    except Exception:
        return ""
    cands = [a for a in re.split(r"[|｜、；;，,（）()\[\]【】\s]+", anchor or "") if len(a) >= min_len]
    cands.sort(key=len, reverse=True)
    for a in cands:
        if norm(a) in txt:
            return a
    whole = norm(anchor or "")
    return anchor if whole and whole in txt else ""


def sentence_around(page_text: str, anchor: str, pad: int = 90) -> str:
    """用定位短语从页面原文里取出**代码自己截的**依据片段（天然逐字）。

    坑（已实测）：`quote_in_page` 用「去掉全部空白」归一化，而这里若只去空格保留换行，
    跨行的定位短语就会在这里找不到 —— 于是依据片段为空，白白把正确答案判成"不同题"。
    所以这里用同一套归一化，并保留「扁平串下标 → 原文下标」的映射，
    好把片段切回原文（保留原有排版），同时保证切片去空白后与扁平串一致。
    """
    flat_chars, orig_idx = [], []
    for i, ch in enumerate(page_text):
        if not ch.isspace():
            flat_chars.append(ch)
            orig_idx.append(i)
    flat = "".join(flat_chars)
    a = re.sub(r"\s+", "", anchor or "")
    if not a:
        return ""
    i = flat.find(a)
    if i < 0:
        return ""
    s = max(0, i - pad)
    e = min(len(flat), i + len(a) + pad)
    frag = page_text[orig_idx[s]: orig_idx[e - 1] + 1]
    return re.sub(r"\s+", " ", frag).strip()


def parse_json(text: str) -> dict:
    """从模型输出里抠出 JSON（容忍 ```json 围栏与前后废话）。"""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.M).strip()
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return {}
    return {}


def norm(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def quote_in_page(rep, page, quote) -> bool:
    """机械核验：quote 必须出现在它自称的那一页原文里（允许空白/换行差异）。"""
    if not page or not quote:
        return False
    try:
        txt = norm(rep.page_text[page - 1])
    except Exception:
        return False
    q = norm(quote)
    if not q:
        return False
    if q in txt:
        return True
    # 容忍 PDF 里的软连字符/全角半角差异
    q2 = q.replace("－", "-").replace("～", "~").replace("（", "(").replace("）", ")")
    t2 = txt.replace("－", "-").replace("～", "~").replace("（", "(").replace("）", ")")
    return q2 in t2


def ask_pages(rep, question: str, pages: list, max_chars_per_page: int = 2600,
              require_keywords: list = None, context_pad: int = 90,
              subject: list = None) -> dict:
    """把候选页原文塞给模型，要求它给出**可回溯**答案。

    三道机械关卡（这是"防编造"的核心，缺一不可）：
      1. 定位短语必须能在它自称的那一页里逐字检索到；检索不到 → 判为编造，留空。
      2. 依据片段由**代码**从页面原文里截取（不是模型给的），因此天然逐字。
      3. 依据必须与结论**同题**：`require_keywords` 命中不了，说明引了不相关句子
         （实测陷阱题就会这样：问海水淡化，它引"供电依托市政电网"）→ 留空。
    """
    blocks = []
    for p in pages:
        t = rep.page_text[p - 1]
        if len(t) > max_chars_per_page:
            t = t[:max_chars_per_page] + "……（本页截断）"
        blocks.append(f"【第{p}页】\n{t}")
    prompt = (f"问题：{question}\n\n"
              f"下面是候选页面的原文（页码即 PDF 物理页）：\n\n" + "\n\n".join(blocks)
              + "\n\n请只依据以上原文回答，严格按三行格式输出：结论、页码、定位短语。"
                "不要输出任何其他内容。")
    t0 = time.time()
    raw = call_model([{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": prompt}])
    out = parse_reply(raw)
    out["_raw"] = raw
    out["_secs"] = round(time.time() - t0, 1)
    out["quote"] = ""
    if out.get("value") is None or not out.get("anchor"):
        out["_verified"] = False
        return out
    pg = out.get("page")
    if not pg or not (1 <= pg <= rep.pages):
        out["_reject"] = "页码缺失或越界"
        out["_verified"] = False
        out["value"] = None
        return out
    matched = match_fragment(rep, pg, out["anchor"])
    if not matched:
        out["_reject"] = "定位短语在该页检索不到任何真实片段 → 判为编造，留空"
        out["_verified"] = False
        out["value"] = None
        return out
    out["_matched"] = matched
    quote = sentence_around(rep.page_text[pg - 1], matched, context_pad)
    # 同题检查对象是**模型给的定位短语**，不是代码截出来的上下文：
    # 上下文里常混着相邻的无关句子，拿它做关键词闸门会误杀正确答案（已实测）。
    if require_keywords and not any(k in out["anchor"] for k in require_keywords):
        out["_reject"] = (f"依据与结论不同题（定位短语未含关键词 {require_keywords}）"
                          f"→ 留空待人工确认")
        out["_verified"] = False
        out["value"] = None
        out["quote"] = quote
        return out
    # 主体词闸门（比同题关键词更硬）：依据必须**明确谈到问题的主体**。
    # 教训（实测）：问"是否涉及集中式饮用水水源/特殊地下水资源保护区"，模型答"否"，
    # 引的却是"防护距离内无环境敏感建筑物" —— 页码真、依据真、还含"保护区"旁边的词，
    # 但根本没谈饮用水/地下水，结论是编的推理而不是报告原话。
    # 通用词（保护区、排放、500…）挡不住这种，主体词（饮用水/水源/矿泉水/温泉/地下水）能。
    if subject and not any(s in out["anchor"] for s in subject):
        out["_reject"] = (f"依据未涉及问题主体（定位短语未含 {subject}）"
                          f"→ 不足以支撑结论，留空待人工确认")
        out["_verified"] = False
        out["value"] = None
        out["quote"] = quote
        return out
    out["quote"] = quote
    out["_verified"] = True
    return out