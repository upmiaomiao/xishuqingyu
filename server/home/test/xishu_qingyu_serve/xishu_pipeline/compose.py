"""把提示词、证据、图片组装成模型消息。

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
from .prompts import PHOTO_JSON_CONTRACT, PHOTO_ROLE_SYSTEM   # noqa: E402


def apply_enhancement(system: str, enhancement: str) -> str:
    """把意图识别生成的「回答质量要求」追加到 system prompt。"""
    enh = (enhancement or "").strip()
    if not enh:
        return system
    return system + f"\n\n【本次回答质量要求】\n{enh}"

def photo_messages(
    context: str,
    image: str | None,
    note: str,
    user_query: str,
    retry: bool = False,
) -> list[dict[str, Any]]:
    """构造现场照片研判的消息。

    关键：**JSON 契约放在 system 里**。实测把它放在 user 消息里会被"看到参考资料就写散文"
    这个训练惯性压过去（正常 RAG 通路的格式也是由 system 控制的，这里与之一致）。
    参考资料同样放 system，避免 user 消息出现"参考资料"字样触发散文模式。
    """
    system = (
        PHOTO_ROLE_SYSTEM
        + "\n\n【可引用依据（参考资料）】\n"
        + context
        + "\n\n"
        + PHOTO_JSON_CONTRACT          # 契约放在最后：临近生成位置，实测首次通过率更高
    )
    if retry:
        system += (
            "\n\n【重要】你上一次的输出不是合法的 JSON，无法被系统解析。"
            "这一次**只输出一个 JSON 对象**，不要任何解释文字、标题、编号或 markdown 代码块。"
        )
    user_text = "请对上面这张现场照片，按系统提示里的 JSON 契约填写。"
    if user_query:
        user_text += f"\n用户补充说明：{user_query}"
    if note:
        user_text += f"\n（系统预先读图结果，仅供参照，可能与图片有出入：{note}）"
    return [{"role": "system", "content": system}, user_message(user_text, image)]

def user_message(text: str, image: str | None) -> dict[str, Any]:
    """构造用户消息；带图时用 OpenAI 兼容的多模态 content 数组。"""
    if not image:
        return {"role": "user", "content": text}
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.append({"type": "image_url", "image_url": {"url": image}})
    return {"role": "user", "content": parts}

