"""后处理：依据白名单校验 + 三态报告渲染。

（由 website_split.py 从单文件服务端机械切分；逻辑未改。）"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

# ---- 同包依赖 ----
from .prompts import PHOTO_ITEM_BANK, PHOTO_REPORT_FOOTER, PHOTO_VERDICTS   # noqa: E402


def photo_render_note(stats: dict[str, int], retried: bool) -> str:
    """把系统的强制/降级动作如实写出来，便于人工复核。"""
    extra = []
    if retried:
        extra.append("首次输出不是合法 JSON，已自动纠错重试一次")
    if stats.get("dropped_items"):
        extra.append(f"过滤了 {stats['dropped_items']} 个不在项目库中的检查项")
    if stats.get("coerced_verdicts"):
        extra.append(f"{stats['coerced_verdicts']} 个越界判定已降级为「无法判断」")
    if stats.get("coerced_stance"):
        extra.append(f"{stats['coerced_stance']} 条风险立场已规范为标准表述")
    return ("\n\n（系统校验：" + "；".join(extra) + "）") if extra else ""

def extract_json_object(text: str) -> dict[str, Any] | None:
    """从模型输出里稳健地取出第一个完整 JSON 对象。"""
    if not text:
        return None
    s = text
    if "</think>" in s:
        s = s.rsplit("</think>", 1)[-1]
    s = s.strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```\s*$", "", s)
    start = s.find("{")
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start:i + 1])
                except Exception:
                    return None
                return obj if isinstance(obj, dict) else None
    return None

def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]

def render_photo_report(data: dict[str, Any]) -> tuple[str, dict[str, int]]:
    """把模型填的 JSON 渲染成固定的七节报告。返回 (报告文本, 统计)。

    代码负责的事：章节顺序、表格结构、三态词表、结论边界、越界项的过滤与计数。
    """
    stats = {"dropped_items": 0, "coerced_verdicts": 0, "coerced_stance": 0}
    lines: list[str] = []

    image_type = str(data.get("image_type") or "").strip() or "其他现场"
    lines.append("【一、图片类型】")
    lines.append(image_type)

    lines.append("")
    lines.append("【二、图中可见事实】")
    facts = [str(x).strip() for x in _as_list(data.get("visible_facts")) if str(x).strip()]
    for i, f in enumerate(facts[:8], 1):
        lines.append(f"{i}. {f}")
    if not facts:
        lines.append("（模型未给出可见事实，需人工查看原图）")

    lines.append("")
    lines.append("【三、核验清单】")
    lines.append("| 检查项 | 图中可见情况 | 判定 | 依据 |")
    lines.append("| --- | --- | --- | --- |")
    rows = 0
    for raw in _as_list(data.get("checklist")):
        if not isinstance(raw, dict):
            stats["dropped_items"] += 1
            continue
        item = str(raw.get("item") or "").strip()
        matched = next((b for b in PHOTO_ITEM_BANK if b == item or (item and (item in b or b in item))), None)
        if matched is None:
            stats["dropped_items"] += 1
            continue                      # 不在项目库里的项直接丢弃，防止模型自造检查项
        observed = str(raw.get("observed") or "").strip() or "照片中不可见"
        verdict = str(raw.get("verdict") or "").strip()
        if verdict not in PHOTO_VERDICTS:
            verdict = "无法判断"           # 词表由代码锁定，越界值一律降级
            stats["coerced_verdicts"] += 1
        basis = str(raw.get("basis") or "").strip() or "依据不足"
        for cell in (matched, observed, verdict, basis):
            if "|" in cell:
                stats["dropped_items"] += 1
                break
        else:
            lines.append(f"| {matched} | {observed} | {verdict} | {basis} |")
            rows += 1
    if rows == 0:
        lines.append("| 无法判断 | 模型未给出有效的核验项 | 无法判断 | 依据不足 |")

    lines.append("")
    lines.append("【四、风险提示】")
    risks = [r for r in _as_list(data.get("risks")) if isinstance(r, dict)]
    for i, r in enumerate(risks[:6], 1):
        level = str(r.get("level") or "").strip() or "中"
        stance = str(r.get("stance") or "").strip()
        if stance not in ("照片已显示", "照片未显示，需核实"):
            stance = "照片未显示，需核实"   # 立场词表同样由代码锁定
            stats["coerced_stance"] += 1
        text = str(r.get("text") or "").strip()
        lines.append(f"{i}. [{level}｜{stance}] {text}")
    if not risks:
        lines.append("（模型未给出风险项）")

    lines.append("")
    lines.append("【五、固废属性初判】")
    lines.append(str(data.get("waste_class") or "").strip() or "照片信息不足，无法作出初步归类。")

    lines.append("")
    lines.append("【六、需要补充的信息】")
    miss = [str(x).strip() for x in _as_list(data.get("missing_info")) if str(x).strip()]
    for i, m in enumerate(miss[:8], 1):
        lines.append(f"{i}. {m}")
    if not miss:
        lines.append("（模型未列出需补充信息）")

    unc = str(data.get("uncertainty") or "").strip()
    if unc:
        lines.append("")
        lines.append(f"（模型自述局限：{unc}）")

    lines.append(PHOTO_REPORT_FOOTER)
    return "\n".join(lines), stats

_NUM_STD_RE = re.compile(r"\b(GB|HJ|CJJ|DB\d{2}|JGJ|SH|JB)\s*/?\s*T?\s*(\d{3,5})(?:[—\-–~]\s*(\d{4}))?", re.I)

_DOC_NAME_RE = re.compile(r"《([^》]{4,60})》")

def _norm_for_match(text: str) -> str:
    """去掉空白、全半角破折号与常见分隔符，便于逐字比对标准编号。"""
    out = (text or "").lower()
    for ch in (" ", "\t", "\n", "\u3000", "—", "–", "~", "－", "(", ")", "（", "）"):
        out = out.replace(ch, "")
    out = out.replace("-", "")
    return out

def _norm_doc_name(name: str) -> str:
    """法规名归一化：容忍"中华人民共和国"前缀的省略，避免把简称误报成编造。"""
    out = _norm_for_match(name)
    return out[7:] if out.startswith("中华人民共和国") else out

def verify_citations(answer: str, sources: list[dict[str, Any]]) -> list[str]:
    """返回「出现在答案里、但检索资料中找不到或年份不符」的依据清单。

    分两类，措辞不同（都只提示人工核对，不指控对错）：
      · 编号未在资料中出现
      · 编号出现但年份与资料不一致（实测抓到过 GB 18599—2023，该标准实为 2020 版）
    """
    if not answer:
        return []
    corpus = _norm_for_match(
        " ".join(f"{s.get('title','')} {s.get('source','')} {s.get('text','')}" for s in sources or [])
    ).replace("中华人民共和国", "")   # 双向容忍简称/全称差异
    missing: list[str] = []
    seen: set[str] = set()

    for m in _NUM_STD_RE.finditer(answer):
        prefix, num, year = m.group(1).upper(), m.group(2), m.group(3)
        full = _norm_for_match(f"{prefix}{num}{year or ''}")
        base = _norm_for_match(f"{prefix}{num}")
        if full in corpus:
            continue
        label = f"{prefix} {num}" + (f"—{year}" if year else "")
        if label in seen:
            continue
        seen.add(label)
        if year and base in corpus:
            missing.append(f"{label}（资料中该编号为其它年份）")
        elif base not in corpus:
            missing.append(label)

    for m in _DOC_NAME_RE.finditer(answer):
        name = m.group(1)
        # 只校验"标准/办法/条例/法/规范/名录/导则/指南/规程"这类正式文件名，
        # 避免把普通引号内容（如《三防》）误判为编造。
        if not re.search(r"(标准|办法|条例|法|规范|名录|导则|规定|细则|指南|规程|技术要求|大纲)$", name):
            continue
        # 4~5 字的"法"多为简称（如《固废法》《大气法》），资料里通常只有全称，跳过以免噪声
        if len(name) <= 5 and name.endswith("法"):
            continue
        if _norm_doc_name(name) not in corpus and name not in seen:
            seen.add(name)
            missing.append(f"《{name}》")
    return missing

def citation_warning(missing: list[str]) -> str:
    """把未在资料中出现的依据做成显式告警，附在报告末尾（不修改模型正文）。"""
    if not missing:
        return ""
    items = "、".join(missing[:8])
    more = f" 等 {len(missing)} 项" if len(missing) > 8 else ""
    return (
        f"\n\n⚠️【依据校验未通过】以下依据没有在本次检索到的资料中逐字出现，"
        f"请人工核对后再对外使用：{items}{more}。"
        f"（本条由系统自动校验生成，不代表正文其他内容有误。）"
    )

