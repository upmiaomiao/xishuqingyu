"""图片理解：识图 + 结果拆分。

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
from .prompts import IMAGE_READ_PROMPT   # noqa: E402
from .textclean import strip_think   # noqa: E402
from .llm import call_model   # noqa: E402


async def read_image(image: str) -> str:
    """把图片交给 v5 多模态通路做「转写 + 描述」，返回纯文本。

    输出约定（见 IMAGE_READ_PROMPT）：第一行是可检索的一句话问题，
    之后一行是 ---，再之后是逐字转写与材料说明。
    用于两种场景：① 用户只发图不打字，需要据此构造检索问题；
    ② 有文字问题时，把识别结果展示给用户核对。
    """
    message, _ = await call_model(
        [
            {"role": "system", "content": "你是图片信息抽取助手，只客观转写和描述图片内容。"},
            {"role": "user", "content": [
                {"type": "text", "text": IMAGE_READ_PROMPT},
                {"type": "image_url", "image_url": {"url": image}},
            ]},
        ],
        900,
        0.0,
    )
    return strip_think(message.get("content") or "")

def split_read_result(text: str) -> tuple[str, str]:
    """把识图输出拆成 (可检索的一句话问题, 详细转写与描述)。

    模型偶尔不按格式输出，此时退化为「取首行当问题、全文当描述」。
    """
    text = (text or "").strip()
    if not text:
        return "", ""
    for sep in ("\n---", "---\n", "\n---\n"):
        if sep in text:
            head, _, tail = text.partition(sep)
            question = head.strip().lstrip("第一行：").strip()
            detail = tail.strip()
            if question and detail:
                return question[:120], detail
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 2 and len(lines[0]) <= 60:
        return lines[0], "\n".join(lines[1:]).strip()
    return text[:120], text

