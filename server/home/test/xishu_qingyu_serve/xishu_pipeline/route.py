"""意图路由：关键词兜底 + 指代消解 + direct_chat / general / rag 判定。

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
from .config import INTENT_API_KEY, INTENT_BASE_URL, INTENT_ENABLED, INTENT_MODEL, INTENT_TIMEOUT   # noqa: E402
from .prompts import INTENT_META_PROMPT   # noqa: E402


_GENERAL_HINTS = (
    "怎么扔", "扔哪", "算哪类", "哪一类垃圾", "算什么垃圾", "干垃圾", "湿垃圾", "厨余", "可回收",
    "找谁", "哪个部门", "打什么电话", "投诉", "举报", "有毒吗", "有没有毒", "会不会", "对身体",
    "危害", "违法吗", "罚款", "多少钱", "免费", "是什么", "是什么意思", "为什么", "有什么区别",
    "该不该", "能不能", "有什么用", "跟我", "跟我们", "日常生活", "老百姓", "居民",
    "我家", "我们小区", "楼下", "附近", "村里", "农村",
)

_PRO_HINTS = (
    "排污许可", "环评", "环境影响评价", "自行监测", "技术规范", "排放标准", "核算", "许可排放量",
    "法典", "法律责任", "行政处罚", "合规", "执法", "验收", "台账", "转移联单", "危废代码",
    "专利", "权利要求", "设计日处理能力", "焚烧炉", "烟气净化", "排放浓度", "标准限值",
)

_PRO_PATTERNS = (
    re.compile(r"第[一二三四五六七八九十百零0-9]{1,4}条"),
    re.compile(r"(GB|HJ|CJJ|DB)\s*/?T?\s*\d{3,}", re.I),
)

_ANAPHORA_RE = re.compile(
    r"^(那|那么|这个|那个|这些|那些|它|它们|他|他们|此|该|上述|前面|刚才|然后|接着|还有|另外|继续|再问|再说)"
    r"|上述|前面(提到|说的|讲的)|刚才(说|提到)|这种|这类|那样"
    r"|该(厂|企业|单位|项目|行为|情况|问题|标准|办法|规定|条款|公司|设施|排放口)"
)

_SHORT_Q_RE = re.compile(r"为什么|怎么办|怎么弄|多久|多少|要罚|会罚|能不能|可以吗|算不算|是吗|呢[？?]?$")

_FILLER_RE = re.compile(
    r"(?:哈|呵|嘿|嘻|嗯|哦|噢|额|呃|唔|嗷)+"
    r"|(?:ok|okay|好的|好|行|可以|收到|明白|知道|了解|谢谢|多谢|感谢|再见|拜拜|bye|thanks|hello|hi|hey)+"
)

def is_public_knowledge(query: str) -> bool:
    """兜底判断：是否为「公众日常/科普」类问题。

    只要出现法规、标准或专业流程特征，一律判为专业问题（继续走 RAG），
    避免把简短的法规追问误判成闲聊。
    """
    q = (query or "").strip()
    if not q or len(q) > 120:
        return False
    lowered = q.lower()
    if any(marker.lower() in lowered for marker in _PRO_HINTS):
        return False
    if any(pattern.search(q) for pattern in _PRO_PATTERNS):
        return False
    return any(marker in q for marker in _GENERAL_HINTS)

def needs_context(query: str) -> bool:
    """判断当前问题是否依赖上文才能理解（指代、省略、极短追问）。

    只有这类问题才允许把上一轮问题带进检索/路由。
    """
    q = (query or "").strip()
    if not q:
        return False
    if _ANAPHORA_RE.search(q):
        return True
    if len(q) <= 8:
        return True
    if len(q) <= 16 and _SHORT_Q_RE.search(q):
        return True
    return False

def fallback_standalone(query: str, history: list[dict[str, str]]) -> str:
    """路由服务不可用时的兜底：只在问题确实依赖上文时才拼接上一轮问题。"""
    q = (query or "").strip()
    if not needs_context(q):
        return q
    prev = next((h["content"] for h in reversed(history or []) if h["role"] == "user"), "")
    return f"{prev}\n当前追问：{q}" if prev else q

async def route_and_enhance(
    query: str, history: list[dict[str, str]] | None = None
) -> tuple[str, str, str]:
    """意图路由：返回 (route, enhancement, standalone_query)。

    standalone_query 是消解了指代后的独立问题，供检索与路由使用；
    识别失败时用关键词兜底并回落到 "rag"，保证专业问答能力不受影响。
    """
    q = (query or "").strip()
    history = history or []
    standalone = fallback_standalone(q, history)
    fallback = "general" if is_public_knowledge(q) else "rag"
    if not INTENT_ENABLED or not q:
        return fallback, "", standalone
    recent = "\n".join(
        f"{'用户' if h['role'] == 'user' else '助手'}：{h['content'][:300]}"
        for h in history[-4:]
    )
    user_content = f"【最近对话】\n{recent}\n\n【用户最新问题】\n{q}" if recent else q
    try:
        async with httpx.AsyncClient(timeout=INTENT_TIMEOUT) as client:
            resp = await client.post(
                f"{INTENT_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {INTENT_API_KEY}"},
                json={
                    "model": INTENT_MODEL,
                    "messages": [
                        {"role": "system", "content": INTENT_META_PROMPT},
                        {"role": "user", "content": user_content},
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1200,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            raw = (data.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
        if not raw:
            return fallback, "", standalone
        if "{" not in raw:
            # 兼容旧格式输出（NO_ENHANCE / 纯质量要求文本）
            return fallback, "", standalone
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            raw = raw[start:end + 1]
        try:
            obj = json.loads(raw)
        except Exception:
            return fallback, "", standalone
        route = str(obj.get("route", "")).strip().lower()
        enhancement = str(obj.get("enhancement") or "").strip()
        rewritten = str(obj.get("standalone_query") or "").strip()
        # 只在明显异常时才拒绝改写结果（过短/过长/仍是占位符）
        if rewritten and 4 <= len(rewritten) <= 400 and not re.match(r"^[.。…\-—]+$", rewritten):
            standalone = rewritten
        if route not in {"rag", "general"}:
            route = fallback
        if route == "general" or "NO_ENHANCE" in enhancement.upper():
            return route, "", standalone
        return "rag", enhancement, standalone
    except Exception:
        return fallback, "", standalone

def is_direct_chat(query: str) -> bool:
    """仅将明确的问候、身份、功能询问和纯应答路由为直接对话。

    其他问题默认仍走 RAG，避免将简短的法规追问误判为闲聊。

    注：原先只认一份很窄的精确白名单，"好的""嗯""在吗""早上好"等都会落到业务
    通道。实测这类没有任何业务内容的输入会诱发模型编造案情（输入"好的"，答出
    "该转运站渗滤液通过暗管外排…已构成环境违法"）。故补齐寒暄/应答，并增加一条
    只匹配"整串都是语气词"的兜底；该兜底要求整串匹配，不会吞掉
    "五年？""可以吗""行吗"这类简短法规追问。
    """
    normalized = re.sub(r"[\s，。！？!?、,.]+", "", query).lower()
    direct_exact = {
        "你好", "您好", "嗨", "hi", "hello", "hey",
        "谢谢", "多谢", "再见",
        "你是谁", "您是谁", "请问你是谁", "请问您是谁",
        "你叫什么", "你叫什么名字", "你的名字是什么",
        "你是什么模型", "你是哪个模型", "你是谁开发的",
        "介绍一下你自己", "请介绍一下你自己", "自我介绍",
        "你能做什么", "你会做什么", "你有什么功能", "你能帮我什么",
        # 寒暄 / 应答：无业务内容，走业务通道会诱发编造
        "好的", "好", "好嘞", "好哒", "行", "可以的", "可以", "收到", "没问题",
        "明白", "明白了", "知道", "知道了", "了解", "了解了", "懂了",
        "嗯", "嗯嗯", "哦", "噢", "呃", "额", "唔",
        "早", "早上好", "上午好", "中午好", "下午好", "晚上好", "晚安", "早安",
        "在", "在吗", "在么", "在不在", "有人吗", "喂", "在的",
        "哈哈", "哈哈哈", "呵呵", "嘿嘿", "嘻嘻",
        "测试", "测试一下", "帮帮我", "我想问个问题",
        "感谢", "多谢了", "拜拜", "bye", "thanks",
    }
    if normalized in direct_exact:
        return True
    # 整串只由语气词/笑声/致意词构成（如"哈哈哈""嗯嗯嗯""好的好的"）。
    # 必须整串匹配，故"五年""可以吗""行吗"这类不会被吞掉。
    return bool(_FILLER_RE.fullmatch(normalized))

