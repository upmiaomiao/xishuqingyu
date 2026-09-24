"""入口规整与校验：所有入口约束的唯一归属。

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
from .config import DEFAULT_TOP_K, MAX_IMAGE_CHARS   # noqa: E402
from .errors import ApiError   # noqa: E402


class HybridSearchRequest(BaseModel):
    query: str | None = Field(default=None, description="用户问题")
    question: str | None = Field(default=None, description="query 的兼容别名")
    top_k: int = Field(default=DEFAULT_TOP_K, ge=1, le=10)
    max_tokens: int = Field(default=8192, ge=128, le=16384)
    temperature: float = Field(default=0.2, ge=0, le=1.5)
    history: list[dict[str, str]] = Field(
        default_factory=list,
        description="此前对话，元素格式为{role:user|assistant, content:string}",
    )
    image: str | None = Field(
        default=None,
        description="单张图片，data URL（data:image/png;base64,...）。只发图不打字时 query 可为空。",
    )
    report: str | None = Field(
        default=None,
        description="报告模式：'photo' = 现场照片专业研判（三态核验清单 + 依据校验）。",
    )

def normalize_image(image: str | None) -> str | None:
    """校验前端传来的图片 data URL。"""
    if not image:
        return None
    image = image.strip()
    if not image.startswith("data:image/"):
        raise ApiError('E_IMAGE_FORMAT', "图片格式不支持，请上传 PNG / JPG / WebP 图片")
    if ";base64," not in image:
        raise ApiError('E_IMAGE_ENCODING', "图片编码格式不正确")
    if len(image) > MAX_IMAGE_CHARS:
        raise ApiError('E_IMAGE_TOO_LARGE', "图片太大，请压缩后重试（建议长边不超过 1600 像素）",)
    return image

def _norm_q(text: str) -> str:
    return re.sub(r"[\s，。！？!?、,.；;：:]+", "", text or "")

def normalize_history(
    history: list[dict[str, str]], query: str = ""
) -> list[dict[str, str]]:
    """整理对话历史。

    两件事很关键：
    1. 用户把同一个问题再问一遍时，把上一轮同样的问答去掉——否则模型会复述旧答案
       （尤其是历史里那轮答错了，会直接把错误结论带进来）。
    2. 助手内容里若残留【分析过程】标记，去掉，避免新回答模仿旧格式。
    """
    cleaned: list[dict[str, str]] = []
    for item in (history or [])[-12:]:
        role = str(item.get("role", "")).strip()
        content = str(item.get("content", "")).strip()[:4000]
        if role not in {"user", "assistant"} or not content:
            continue
        if role == "assistant":
            content = re.sub(r"^【分析过程】[\s\S]*?【(?:回答|答案|结论)】\s*", "", content).strip()
            content = re.sub(r"^【(?:分析过程|回答|答案|结论)】\s*", "", content).strip()
            if not content:
                continue
        cleaned.append({"role": role, "content": content})
    nq = _norm_q(query)
    if nq and len(cleaned) >= 2:
        tail = cleaned[-2:]
        if tail[0]["role"] == "user" and _norm_q(tail[0]["content"]) == nq:
            cleaned = cleaned[:-2]
    return cleaned

