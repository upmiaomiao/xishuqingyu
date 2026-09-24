"""文本清洗：模型口吻、标记、免责尾段、PDF 乱码。

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


_TAIL_MARKER = re.compile(r"\n[ \t]*(?:此外|另外|需要说明的是|值得说明的是|补充说明)[，,：:]")

_DISCLAIMER_WORDS = (
    "未提供", "未给出", "未明确", "未说明", "无法判断", "无法确定", "不能确定", "无法量化",
    "未证明", "证据", "材料", "无法回答", "无法给出", "无法对", "题目未", "该题未",
)

_INLINE_EVIDENCE = re.compile(
    r"(?m)^[ \t]*(?:根据现有证据|根据所给材料|根据材料|材料显示|从材料看|现有证据表明|"
    r"根据现有资料|依据现有资料|根据所给资料)[，,]\s*"
)

_TAIL_HOLD_LIMIT = 400  # 尾段超过这个长度就认为不是免责段，放行

_SENT_END = re.compile(r"[。！？!?\n]")

# ---- LaTeX 公式还原（2026-09-19）----
# 语料里标准/导则的数值大量以 LaTeX 形式存在（PDF→md 转换留下的），
# 例如「不大于$1.0{\times}10^{-5}\,\mathrm{cm/s}$」。这些数值恰恰是专业问答的答案本体，
# 因此清洗只能"翻译"不能"删除"。长命令必须排在短命令前面（\leq 先于 \le）。
_LATEX_SYMBOLS = (
    ("\\times", "×"), ("\\cdot", "·"), ("\\div", "÷"),
    ("\\leq", "≤"), ("\\le", "≤"), ("\\geq", "≥"), ("\\ge", "≥"),
    ("\\neq", "≠"), ("\\approx", "≈"), ("\\sim", "~"), ("\\pm", "±"),
    ("\\infty", "∞"), ("\\rightarrow", "→"), ("\\to", "→"),
    ("\\cdots", "…"), ("\\ldots", "…"), ("\\dots", "…"),
    ("\\alpha", "α"), ("\\beta", "β"), ("\\gamma", "γ"), ("\\delta", "δ"),
    ("\\mu", "μ"), ("\\rho", "ρ"), ("\\sigma", "σ"), ("\\lambda", "λ"),
    ("\\theta", "θ"), ("\\omega", "ω"), ("\\circ", "°"),
    ("\\%", "%"), ("\\&", "&"), ("\\_", "_"),
    ("\\quad", " "), ("\\qquad", " "), ("\\,", " "), ("\\;", " "),
    ("\\:", " "), ("\\!", ""), ("\\ ", " "), ("\\~", " "),
)

_LATEX_TEXT_CMD = re.compile(
    r"\\(?:mathrm|text|mathbf|mathit|mathsf|mathtt|operatorname|textbf|textit|mbox|textnormal)"
    r"\s*\{([^{}]*)\}"
)

_SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻", "+": "⁺"}

def _sup(match: re.Match) -> str:
    """^-5 → ⁻⁵（上标必须保住：10⁻⁵ 与 10⁵ 差一个数量级）"""
    return "".join(_SUP.get(ch, ch) for ch in match.group(1))

def demath(span: str) -> str:
    """把一段 LaTeX 转成可读纯文本；数值与单位必须原样保住。

    `1.0{\\times}10^{-5}\\,\\mathrm{cm/s}` → `1.0×10⁻⁵ cm/s`
    """
    s = span
    s = re.sub(r"\\(?:left|right|displaystyle|textstyle|limits|nolimits)\b", "", s)
    # 语料里 `10^{\cdot7}` 是 `10^{-7}` 的 PDF 提取变形（点号实为负号），先纠正
    s = re.sub(r"\^\s*\{\s*\\cdot\s*", "^{-", s)
    for _ in range(3):                     # \mathrm{\times} 这类嵌套要反复剥
        s = _LATEX_TEXT_CMD.sub(r"\1", s)
    s = re.sub(r"\\frac\s*\{([^{}]*)\}\s*\{([^{}]*)\}", r"\1/\2", s)
    s = re.sub(r"\\sqrt\s*\{([^{}]*)\}", r"√\1", s)
    s = re.sub(r"\^\s*\{([^{}]*)\}", r"^\1", s)
    s = re.sub(r"\^\s*(-?[\d]+)", _sup, s)
    s = re.sub(r"_\s*\{([^{}]*)\}", r"\1", s)
    # 公式里的裸 ~ 是不换行空格，必须**先**清掉；否则后面 \sim→~ 会被它一起吃掉，
    # "$6{\sim}9$" 就会从「6~9」变成「6 9」，读起来像两个独立的数。
    s = s.replace("~", " ")
    for k, v in _LATEX_SYMBOLS:
        s = s.replace(k, v)
    s = re.sub(r"\\[a-zA-Z]+\b", " ", s)   # 认不出来的命令，宁可去掉
    s = re.sub(r"[{}]", "", s)
    return re.sub(r"\s+", " ", s).strip()

_INLINE_AUDIT = re.compile(
    r"(?:(但|不过|然而|因此|所以|而且|同时)\s*)?(?:在)?\s*"
    r"(?:现有|所给|上述|本|科普|相关)?(?:材料|证据|指南|标准|规范|文件)(?:中|里)?\s*"
    r"(?:并未|未|没有|尚未)\s*"
)

_INLINE_EVIDENCE2 = re.compile(
    r"(?:因此|所以|故|但|不过)?\s*(?:基于|根据)(?:现有|上述|所给)?(?:证据|材料)[，,]\s*"
)

def strip_audit_words(text: str) -> str:
    """把句中残留的审查腔改写成平实说法。

    只替换"主体+否定"这一小段（保留后面的动词和宾语，也保留转折连词），
    所以句子依然通顺："但证据未规定举报人保护" → "但目前尚未规定举报人保护"。
    """
    if not text:
        return text
    out = _INLINE_EVIDENCE2.sub("", text)
    return _INLINE_AUDIT.sub(lambda m: f"{m.group(1) or ''}目前尚未", out)

def clean_general_answer(text: str) -> str:
    """非流式：删掉结尾的免责尾段，并清掉段首的审查式措辞。"""
    out = (text or "").strip()
    if not out:
        return out
    for m in reversed(list(_TAIL_MARKER.finditer(out))):
        tail = out[m.start():]
        if len(tail) <= _TAIL_HOLD_LIMIT and any(w in tail for w in _DISCLAIMER_WORDS):
            out = out[: m.start()].rstrip()
            break
    out = _INLINE_EVIDENCE.sub("", out)
    out = strip_audit_words(out)
    return re.sub(r"\n{3,}", "\n\n", out).strip()

class GeneralTailGuard:
    """流式：尾段免责说明截住不发；并按句做句中审查腔清洗。

    按句输出的原因：审查腔可能在句中（"但证据未规定…"），逐 chunk 输出会漏掉
    跨 chunk 的片段，所以攒够一整句再清洗后发出。缓冲区超过 120 字也强制放行，
    避免长句无标点时卡住。
    """

    def __init__(self) -> None:
        self.buf = ""
        self.holding = False

    def feed(self, text: str) -> str:
        self.buf += text
        out = ""
        if not self.holding:
            m = _TAIL_MARKER.search(self.buf)
            if m:
                out, self.buf = self.buf[: m.start()], self.buf[m.start():]
                self.holding = True
        if not self.holding:
            cut = 0
            for m in _SENT_END.finditer(self.buf):
                cut = m.end()
            if cut:
                out += self.buf[:cut]
                self.buf = self.buf[cut:]
            elif len(self.buf) > 120:
                out += self.buf
                self.buf = ""
        if self.holding and len(self.buf) > _TAIL_HOLD_LIMIT:
            out += self.buf
            self.buf = ""
            self.holding = False
        return strip_audit_words(out)

    def flush(self) -> str:
        held, self.buf = self.buf, ""
        if self.holding and len(held) <= _TAIL_HOLD_LIMIT and any(w in held for w in _DISCLAIMER_WORDS):
            return ""
        return strip_audit_words(held)

def strip_think(text: str) -> str:
    """只取 </think> 之后的正文；模型偶尔会把分节标题也带出来，这里一并去掉。"""
    if not text:
        return ""
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1]
    text = re.sub(r"^\s*(【问题识别】|【规则逻辑】|【逐项分析】|【要点】)\s*", "", text.strip())
    return text.strip()

def clean_retrieved_text(text: str) -> str:
    """清掉检索片段里的乱码，但**保住公式里的数值**。

    2026-09-19 修正：旧实现把成对的 `$...$` 整段替换成空格，等于在送进模型之前
    就把标准限值删掉了 —— 语料里 GB 18599-2020 的 I 类场防渗要求写作
    `$1.0{\\times}10^{-5}\\,\\mathrm{cm/s}$`，清洗后只剩空格，于是出现
    "引用是对的、答案却说数值缺失"这种自相矛盾。现在改为先还原成可读文本
    （符号映射 + 上标保留 + 下标拉平 + 去命令），再清残留，最后才丢垃圾。
    """
    if not text:
        return text
    out = re.sub(r"\$([^$\n]{1,200})\$", lambda m: " " + demath(m.group(1)) + " ", text)
    out = out.replace("$", " ")                        # 落单的 $ 直接去掉
    out = re.sub(r"\\[a-zA-Z]{2,}", " ", out)          # 公式外的残留命令 \mathrm \left 之类
    # 清洗后可能留下空括号，模型会照抄成"排放口6个（）"，必须一并去掉
    out = re.sub(r"[（(]\s*[）)]", "", out)
    out = re.sub(r"[【\[]\s*[】\]]", "", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()

def split_public_reasoning(
    content: str | None,
    reasoning_content: str | None,
) -> tuple[str, str]:
    """优先使用推理接口的独立字段；否则拆分模型显式生成的公开分析摘要。"""
    answer = (content or "").strip()
    reasoning = (reasoning_content or "").strip()
    if not reasoning and "</think>" in answer:
        reasoning, answer = answer.split("</think>", 1)
        reasoning = reasoning.strip()
        answer = answer.strip()
    if not reasoning:
        match = re.search(
            r"【分析过程】\s*(.*?)\s*【(?:答案|回答|结论)】\s*(.*)",
            answer,
            flags=re.S,
        )
        if match:
            reasoning, answer = match.group(1).strip(), match.group(2).strip()
    # 兜底：单独出现（没有配对的【分析过程】）的标记也要清掉，
    # 否则会像 <answer> 一样直接显示给用户。
    answer = re.sub(r"</?answer>", "", answer, flags=re.I)
    answer = re.sub(r"^\s*【(?:分析过程|回答|答案|结论)】\s*", "", answer)
    answer = re.sub(r"\s*【(?:分析过程|回答|答案|结论)】\s*$", "", answer)
    return reasoning, answer.strip()

