#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""② 抽取层 · 模型兜底：语义型判据输入 + 名录条件逐条核实。

分工（为什么要分开）：
  · 表驱动抽取（extract.py）：物料、风险物质、敏感目标 —— 报告写得规整，代码读得更准。
  · 模型抽取（本文件）：废水去向、取水水源、名录定性条件等**语义型**问题 ——
    正则必假阳性（已实测两条），交给模型读原文，再由代码机械核验。
  · 两部分都产出 `page + quote`，且都过同一条核验（原文必须能在该页检索到）。

每个问题都限定**机械缩小后的候选页**，既不喂整本报告（省 token），也不让模型自由联想。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from audit.llm import ask_pages, quote_in_page, sentence_around  # noqa: E402

PROMPT_VERSION = "v11"    # 改问法 / 改关键词闸门 / 改候选页策略 / 改事实卡片时递增

# 每个问题：key / 问法 / 用于缩小候选页的正则 / 锚点 / 依据须命中的关键词
QUESTIONS = [
    {
        "key": "废水是否直排",
        "q": ("本项目运营期废水的最终去向是什么？请判断是否属于『直接排入环境水体（直排）』。"
              "若废水经厂内处理后纳入市政管网、进入污水处理厂，或全部回用不外排，"
              "则**不属于**直排，答案应为『否』。（关键词：废水、污水、排放、接管、回用）"),
        "hints": [r"排放去向|纳污|接管|纳入.{0,10}(管网|污水处理厂)|不外排|全部回用|零排放"],
        "anchors": ["水平衡", "地表水", "产污环节"],
        "kw": ["废水", "污水", "排放", "接管", "回用", "排入"],
        # 主体词：依据必须明确谈到"废水/污水"，只谈"排放（标准/口）"不算
        "subject": ["废水", "污水", "生产废", "生活污"],
    },
    {
        "key": "是否新增河道取水",
        "q": ("本项目生产/生活用水的水源是什么？是否属于『新增河道（地表水）取水』？"
              "若水源为市政自来水或市政供水管网，则**不属于**新增河道取水，答案应为『否』。"
              "（关键词：取水、水源、用水、供水）"),
        "hints": [r"给水[：:]|用水由|水源为|取自|取水口|供水管网|市政.{0,6}(供水|管网|自来水)"],
        "anchors": ["水平衡", "地表水"],
        "kw": ["取水", "水源", "用水", "供水", "给水", "管网", "自来水"],
        "subject": ["取水", "水源", "自来水", "给水", "供水"],
    },
    {
        "key": "是否涉及集中式饮用水水源或特殊地下水资源保护区",
        "q": ("本项目评价范围内是否涉及集中式饮用水水源保护区，"
              "或矿泉水、温泉等特殊地下水资源保护区？涉及则答『是』，明确不涉及答『否』。"
              "（关键词：饮用水水源、保护区、矿泉水、温泉、地下水）"),
        "hints": [r"饮用水水源|饮用水源|水源保护区|矿泉水|温泉|地热水|地下水资源保护"
                  r"|不[属涉][于及][^。]{0,20}(饮用水|水源|地下水)"],
        "anchors": ["地下水", "环境敏感目标"],
        "kw": ["饮用水", "水源", "保护区", "矿泉水", "温泉", "地下水"],
        # 只谈"保护区/敏感目标"不能支撑本题结论，必须是饮用水源地/地下水这类主体
        "subject": ["饮用水", "水源", "矿泉水", "温泉", "地下水", "补给区"],
    },
    {
        "key": "厂界外500米内是否有环境空气保护目标",
        "q": ("本项目厂界外 500 米范围内是否存在**环境空气保护目标**"
              "（居民点、村庄、学校、医院、疗养院等）？存在答『是』，"
              "报告明确写明范围内没有答『否』。（关键词：环境空气、保护目标、居民、村庄、500）"),
        "hints": [r"500\s*m|环境保护目标|环境空气保护目标|敏感目标"],
        "anchors": ["环境敏感目标"],
        "kw": ["保护目标", "居民", "村庄", "敏感", "500", "环境空气", "花园", "小区"],
        "subject": ["保护目标", "居民", "村庄", "学校", "医院", "敏感", "花园", "小区"],
    },
    {
        "key": "取水口下游500米内是否有重要水生生物三场一通道",
        "q": ("本项目取水口下游 500 米范围内是否存在重要水生生物的自然产卵场、索饵场、"
              "越冬场和洄游通道？存在答『是』，明确没有或不涉及取水口答『否』。"
              "（关键词：取水口、水生生物、产卵场、索饵场、越冬场、洄游）"),
        "hints": [r"产卵场|索饵场|越冬场|洄游通道|三场一通道|水生生物"],
        "anchors": ["生态", "地表水"],
        "kw": ["产卵场", "索饵场", "越冬场", "洄游", "水生生物", "取水口"],
        # 只出现"取水口"不算（实测：有答案引了取水口的句子来回答三场一通道）
        "subject": ["产卵场", "索饵场", "越冬场", "洄游", "水生生物", "三场"],
    },
    {
        "key": "是否属于污染影响类且新增河道取水",
        "q": ("本项目是否属于**新增河道（地表水）取水**的建设项目？"
              "只有明确写了新增河道/地表水取水才答『是』，水源为市政管网答『否』。"
              "（关键词：取水、河道、地表水、水源）"),
        "hints": [r"新增.{0,8}(河道|地表水).{0,4}取水|河道取水|地表水取水"],
        "anchors": ["水平衡"],
        "kw": ["取水", "河道", "地表水", "水源", "用水", "给水"],
        "subject": ["取水", "河道", "水源"],
    },
]


def candidate_pages(rep, spec, max_pages: int = 8) -> list:
    """机械缩小候选页：**正则命中页优先**，锚点页补充，去重后截断。

    顺序有讲究（已实测踩坑）：锚点页常常一口气占满预算（地下水锚点 ±2 就是 5 页），
    把真正含结论的那一页挤掉 —— 玻璃报告表就因此漏掉了 P29 那句
    "项目选址不属于生活饮用水源地和地下水补给区…"，问题被误判成"报告没写"。
    """
    pages = []
    for rx in spec.get("hints", []):
        for h in rep.search(rx, max_hits=3):
            pages.append(h["page"])
    for anc in spec.get("anchors", []):
        for h in rep.anchors.get(anc, [])[:1]:
            pages += list(range(max(1, h["page"] - 1), min(rep.pages, h["page"] + 2) + 1))
    seen, out = set(), []
    for p in pages:
        if p not in seen and 1 <= p <= rep.pages:
            seen.add(p)
            out.append(p)
    return out[:max_pages]


def _cache_path(cache_dir, sha1, key):
    # 缓存键必须带**提示词版本**：改了问法/关键词闸门后，旧缓存会让改动看起来没生效
    # （本项已实测踩过一次：改了关键词但命中的是旧缓存，输出还是旧拦截理由）
    h = hashlib.sha1(f"{PROMPT_VERSION}|{sha1}|{key}".encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, "llm", f"{h}.json")


def _read_cache(path):
    if path and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def _write_cache(path, obj):
    if not path:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def llm_inputs(rep, cache_dir: str = None, keys: list = None,
               max_pages: int = 6, verbose: bool = False, skip: set = None) -> dict:
    """跑完所有语义型问题，返回 {key: {value, page, quote, method, verified}}。

    `skip`：已经由表驱动机械判定、无需再问模型的键。
    """
    out = {}
    skip = skip or set()
    for spec in QUESTIONS:
        if keys and spec["key"] not in keys:
            continue
        if spec["key"] in skip:
            continue
        cp = _cache_path(cache_dir, rep.sha1, spec["key"]) if cache_dir else None
        r = _read_cache(cp)
        if r is not None:
            r["method"] = "llm(缓存)"
            if verbose:
                print(f"    · {spec['key']}: {r.get('value')} (P{r.get('page')}, 缓存)")
            out[spec["key"]] = r
            continue
        pages = candidate_pages(rep, spec, max_pages)
        if not pages:
            out[spec["key"]] = {"value": None, "page": None, "quote": "",
                                "method": "llm", "verified": False,
                                "note": "候选页为空，未调用模型"}
            continue
        try:
            r = ask_pages(rep, spec["q"], pages, require_keywords=spec["kw"],
                          subject=spec.get("subject"))
        except Exception as exc:                      # 模型服务不可用不能拖垮审核
            out[spec["key"]] = {"value": None, "page": None, "quote": "",
                                "method": "llm", "verified": False,
                                "note": f"模型调用失败：{exc}"}
            continue
        r = {k: v for k, v in r.items() if k != "_raw"}
        r["method"] = "llm"
        r["candidate_pages"] = pages
        out[spec["key"]] = r
        _write_cache(cp, r)
        if verbose:
            print(f"    · {spec['key']}: {r.get('value')} (P{r.get('page')}, "
                  f"verified={r.get('_verified')}, {r.get('_secs')}s)"
                  + (f"  !! {r['_reject']}" if r.get("_reject") else ""))
    return out


def _core_words(raw: str, n: int = 5) -> list:
    """从条件原文里抽**主题词**，用作同题闸门的关键词。

    坑（已实测）：拿整个条件原文当关键词会误杀正确答案 —— 问"是否属于平板玻璃制造"，
    报告的合法依据是产品描述"年产18万吨建筑节能玻璃及太阳能光伏玻璃"，
    它当然不会出现"平板玻璃制造"四个字。所以这里抽出 2 字主题词
    （玻璃、电镀、切割…），只要依据谈的是同一件事就放行。
    """
    main = re.split(r"[（(]|除外", raw)[0]
    main = re.sub(r"^(有|属于|涉及|为|以|使用|采用|全部|其他|仅|不)", "", main.strip()).rstrip("的")
    words = []
    for w in re.split(r"[；;、，,]|和|及", main):
        w = w.strip()
        if len(w) < 2:
            continue
        words.append(w)
        if len(w) >= 4:
            words += [w[i:i + 2] for i in range(len(w) - 1)]
    seen, out = set(), []
    for w in words:
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:n] or [main[:4]]


def llm_conditions(rep, item: dict, cache_dir: str = None, verbose: bool = False,
                   max_pages: int = 5, tiers=("报告书", "报告表"),
                   digest: str = "", stated: str = "", stated_page: int = None) -> list:
    """把名录条目里**还没有事实可核的定性条件**逐条问模型，产出带原文的事实。

    为什么必须逐条问：名录一个条目下有三档、每档若干并列条件（「或」关系）。
    报告往往只自述其中一条情形，其余条件就没有事实可核 → 判据层只能答"不确定"
    → 审核意见永远停在"存在疑似问题"，工具就没用了。
    逐条问 + 原文核验，既能真正锁定档位，又不会让模型凭空断案。

    `digest`：项目事实卡片（带页码）。没有它模型会引用"见见表2-2"这种指引句当依据。
    """
    out = []
    for tier in tiers:
        for c in item["_cond"].get(tier, []):
            if c.kind != "qualitative" or c.raw.strip().startswith("其他"):
                continue
            # **先做机械判定**：报告自己写的名录自述里若直接出现该情形，就不必问模型。
            # 报告自述是最硬的证据（比任何推断都硬），而且这一步是确定性的、可复现的。
            base = re.sub(r"[（(][^）)]*[）)]", "", c.raw).strip()
            if stated and base and base in stated and stated_page:
                q_ok = quote_in_page(rep, stated_page, base)
                if q_ok:
                    if verbose:
                        print(f"      · 条件『{c.raw[:26]}』→ True (P{stated_page}, 名录自述)")
                    out.append({"raw": c.raw, "present": True, "page": stated_page,
                                "quote": sentence_around(rep.page_text[stated_page - 1], base, 90),
                                "tier": tier, "method": "名录自述"})
                    continue
            pages = []
            for anc in ("产品方案", "工艺流程", "原辅材料", "项目概况", "产污环节"):
                for h in rep.anchors.get(anc, [])[:1]:
                    pages += list(range(max(1, h["page"] - 1), min(rep.pages, h["page"] + 2) + 1))
            seen, cp = set(), []
            for p in pages:
                if p not in seen and 1 <= p <= rep.pages:
                    seen.add(p)
                    cp.append(p)
            cp = cp[:max_pages]
            # 名录自述所在的页**必须**进候选：报告往往只在那一页写明"属于哪个情形"，
            # 而那一页通常既不是产品方案页也不是工艺页（实测：白银的自述在第8页）。
            if digest:
                extra = [int(m.group(1)) for m in re.finditer(r"【第(\d+)页】[^\n]*名录", digest)]
                cp = list(dict.fromkeys(extra + cp))[:max_pages + 2]
            key = f"条件::{item['no']}::{c.raw}"
            path = _cache_path(cache_dir, rep.sha1, key) if cache_dir else None
            r = _read_cache(path)
            if r is None:
                if not cp:
                    continue
                # 问法说明：**不要**在问句里强调《分类管理名录》。
                # 实测教训：一问"是否属于名录情形"，模型就跑去翻"编制依据"章节，
                # 那里只有名录书名、没有条目名，于是答"不确定"——临沂报告书因此从
                # "无问题"退回"疑似"。改成问产品/原料/工艺/建设内容，模型回到正题。
                # 而白银那种"报告自己写明了名录情形"的情况，已由上面的**机械自述路径**兜住，
                # 不再依赖问法（机械路径比问模型更硬、也更可复现）。
                q = (f"本项目的产品、原料、工艺或建设内容是否属于以下情形：『{c.raw}』？"
                     f"能判断属于答『是』；能判断不属于（产品/工艺与该情形明显不同，"
                     f"或报告写明『不涉及』『除外』）答『否』；"
                     f"报告完全没写相关信息、无从判断才答『不确定』。"
                     f"（关键词：{'、'.join(_core_words(c.raw))}）")
                if digest:
                    q += ("\n\n以下是本项目的事实卡片（每行都标了 PDF 物理页页码，"
                          "可以直接引用其中的片段作为定位短语）：\n" + digest)
                try:
                    r = ask_pages(rep, q, cp, require_keywords=_core_words(c.raw))
                except Exception as exc:
                    r = {"value": None, "page": None, "anchor": "", "quote": "",
                         "verified": False, "note": f"模型调用失败：{exc}"}
                r = {k: v for k, v in r.items() if k != "_raw"}
                r["method"] = "llm(条件)"
                r["candidate_pages"] = cp
                _write_cache(path, r)
            r["condition"] = c.raw
            r["tier"] = tier
            if verbose:
                print(f"      · 条件『{c.raw[:26]}』→ {r.get('value')} "
                      f"(P{r.get('page')}, verified={r.get('_verified')})"
                      + (f" !! {r['_reject']}" if r.get("_reject") else ""))
            if r.get("value") is not None and r.get("_verified"):
                out.append({"raw": c.raw, "present": bool(r["value"]),
                            "page": r.get("page"), "quote": r.get("quote", ""),
                            "tier": tier})
    return out