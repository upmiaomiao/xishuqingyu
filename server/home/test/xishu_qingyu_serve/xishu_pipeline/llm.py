"""底层模型调用（流式与非流式）。

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
from .config import MODEL_NAME, MODEL_URL   # noqa: E402
from .errors import ApiError   # noqa: E402


async def call_model(
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": True},
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=600) as client:
        try:
            response = await client.post(MODEL_URL, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ApiError('E_MODEL_UNAVAILABLE', f"模型服务异常：{exc}")
    data = response.json()
    return data["choices"][0]["message"], data

async def stream_model(
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    usage_out: dict[str, Any] | None = None,
    response_format: dict[str, Any] | None = None,
):
    """流式调用 v5，逐段 yield content 增量。

    usage_out：可选的可变字典。传入后会把服务端返回的 usage 写进 usage_out["usage"]，
    供**非流式端点**在消费同一事件流时拼出与改动前一致的 usage 字段。

    response_format：可选的结构化输出约束（如 {"type": "json_object"}）。
    **默认 None = 与改动前逐字节一致**，只有需要 JSON 的通路（现场照片研判）才传。
    为什么需要它：照片研判的 JSON 契约写在 system 里，但实测模型会「读懂契约却用散文复述」
    （输出里一个 `{` 都没有），extract_json_object 于是返回 None、结构化渲染整条失效。
    加该参数后实测首次即通过（核验清单 7 项，dropped_items=0、coerced_verdicts=0）。
    """
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.9,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": True},
        "stream": True,
        # 让 vLLM 在最后一个 chunk 里带上 usage；不支持的实现会忽略该字段，不影响正文
        "stream_options": {"include_usage": True},
    }
    if response_format:
        payload["response_format"] = response_format
    async with httpx.AsyncClient(timeout=600) as client:
        async with client.stream("POST", MODEL_URL, json=payload) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    d = json.loads(data)
                except Exception:
                    continue
                if usage_out is not None and d.get("usage"):
                    usage_out["usage"] = d["usage"]
                choices = d.get("choices") or []
                if not choices:          # include_usage 的收尾块 choices 为空，不能索引
                    continue
                delta = choices[0].get("delta", {}) or {}
                content = delta.get("content") or ""
                if content:
                    yield content

