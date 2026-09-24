"""流式输出拆分器：<think>…</think> → reasoning / answer。

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


class ThinkAnswerSplitter:
    """把 v4 的 <think>…</think>\n\n答案 流式拆成 reasoning / answer，处理 </think> 跨 chunk 边界。

    另外清洗模型偶发套在答案外面的标记：<answer>…</answer>、【回答】、【答案】、【结论】。
    实测（41 题抽样）约 19% 的问候类回答会把 <answer> 一起发出来；非流式路径
    split_public_reasoning 恰好会剥掉它，所以只在流式（前端实际走的接口）上暴露。
    标记可能被 SSE 切成两半，故按最长标记长度在缓冲区末尾做 holdback。
    若 </think> 之后模型又写了「【分析过程】…【回答】…」，前半段归入 reasoning。
    """

    # 注：原来这里手写过一份 </think> 的前缀表，漏了 7 字符的 "</think"，
    # 导致缓冲区正好停在该长度时会把 "</think" 当推理发出去、think_done 永不置位。
    # 现统一用 _holdback 计算，不再维护前缀表。
    _MARKERS = ("<answer>", "</answer>", "<think>", "</think>", "【分析过程】", "【回答】", "【答案】", "【结论】")
    _LEAD = ("<answer>", "【分析过程】", "【回答】", "【答案】", "【结论】")
    _ANALYSIS_END = ("【回答】", "【答案】", "【结论】")
    _MAXM = max(len(m) for m in _MARKERS)

    def __init__(self) -> None:
        self.buf = ""
        self.think_done = False
        self.answer_started = False
        self.at_lead = True        # 仍在答案开头、可剥离开头标记
        self.in_analysis = False   # 正在输出【分析过程】内容，应归入 reasoning
        self.head = ""             # 流的开头若干字符，用于判定"有没有 think 块"
        self.head_resolved = False

    def _emit_chunk(self, text: str) -> str:
        if not self.answer_started:
            self.answer_started = True
            text = text.lstrip("\r\n ")
        return text

    @staticmethod
    def _holdback(text: str, markers: tuple[str, ...]) -> int:
        """返回需留在缓冲区末尾的字符数，避免把跨 chunk 的标记发出去。"""
        for k in range(min(len(text), ThinkAnswerSplitter._MAXM - 1), 0, -1):
            tail = text[-k:]
            if any(m.startswith(tail) for m in markers):
                return k
        return 0

    def _process_answer(self, text: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        self.buf += text
        while True:
            if self.in_analysis:
                idx, hit = -1, ""
                for m in self._ANALYSIS_END:
                    j = self.buf.find(m)
                    if j != -1 and (idx == -1 or j < idx):
                        idx, hit = j, m
                if idx == -1:
                    safe = len(self.buf) - self._holdback(self.buf, self._ANALYSIS_END)
                    if safe > 0:
                        out.append(("reasoning", self.buf[:safe]))
                        self.buf = self.buf[safe:]
                    return out
                if idx > 0:
                    out.append(("reasoning", self.buf[:idx]))
                self.buf = self.buf[idx + len(hit):]
                self.in_analysis = False
                self.at_lead = True
                continue

            if self.at_lead:
                stripped = self.buf.lstrip()
                matched = next((m for m in self._LEAD if stripped.startswith(m)), "")
                if matched:
                    self.buf = stripped[len(matched):]
                    if matched == "【分析过程】":
                        self.in_analysis = True
                    continue
                if not stripped:
                    self.buf = ""
                    return out          # 只有空白：继续等，at_lead 保持
                if len(stripped) < self._MAXM and any(m.startswith(stripped) for m in self._LEAD):
                    return out          # 可能是标记的前半截
                self.buf = stripped
                self.at_lead = False

            safe = len(self.buf) - self._holdback(self.buf, self._MARKERS)
            if safe <= 0:
                return out
            piece = self.buf[:safe]
            self.buf = self.buf[safe:]
            for m in self._MARKERS:
                piece = piece.replace(m, "")
            if piece:
                if not self.answer_started:
                    self.answer_started = True
                    piece = piece.lstrip("\r\n ")
                if piece:
                    out.append(("chunk", piece))
            return out

    def _head_verdict(self) -> bool | None:
        """开头判定：True=确实以「答案格式标记」开头；False=不是；None=还看不出来。

        **为什么不能靠"开头是不是 <think"来判有没有 think 块**：
        实测本模型（vLLM + chat_template_kwargs.enable_thinking）**只输出收尾的 `</think>`**，
        正文开头直接就是推理内容（原始 SSE 第一块 content='问题'、通篇没有 `<think>`）。
        所以"开头不是 <think"根本不能说明没有 think 块——第一版据此判定，把整段推理内容
        当成了答案输出（reasoning 块数直接掉到 0）。
        只有开头落在 `<answer>`/`【分析过程】`/`【回答】` 这类**答案格式标记**上时，
        才可以断定模型没写 think 块。
        """
        hs = self.head.lstrip()
        if not hs:
            return None
        for m in self._LEAD:
            if len(hs) >= len(m):
                if hs.startswith(m):
                    return True
            elif m.startswith(hs):
                return None          # hs 是某个标记的前缀，再等等
        return False

    def feed(self, content: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self.think_done:
            self.buf += content
            # 开头判定：模型没写 think 块、直接给答案格式时，必须尽早转答案模式。
            # 否则 _process_answer 永远不会被调用，<answer>、【回答】等标记不会被剥离。
            if not self.head_resolved:
                self.head += content
                verdict = self._head_verdict()
                if verdict is True:
                    self.head_resolved = True
                    self.think_done = True
                    pending, self.buf = self.buf, ""
                    return out + self._process_answer(pending)
                if verdict is False:
                    self.head_resolved = True          # 普通正文，继续按推理处理
                elif len(self.head) > 64:
                    self.head_resolved = True
                    verdict = False
                if verdict is None:
                    return out      # 还看不出：先攒着（最多几个字符），不往 reasoning 发

            idx = self.buf.find("</think>")
            if idx != -1:
                if idx > 0:
                    out.append(("reasoning", self.buf[:idx]))
                self.think_done = True
                rest = self.buf[idx + len("</think>"):]
                self.buf = ""
                if rest:
                    out.extend(self._process_answer(rest))
                return out
            safe = len(self.buf) - self._holdback(self.buf, ("</think>",))
            if safe > 0:
                out.append(("reasoning", self.buf[:safe]))
                self.buf = self.buf[safe:]
            return out

        out.extend(self._process_answer(content))
        return out

    def flush(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if not self.buf:
            return out
        if not self.think_done:
            # 到流结束都没出现 </think>：保持原行为，整段归入 reasoning。
            # 不把它当答案——那和"推理被 max_tokens 截断"无法区分，误标比不标更糟。
            out.append(("reasoning", self.buf))
            self.buf = ""
            return out
        pending, self.buf = self.buf, ""
        if self.in_analysis:
            for m in self._ANALYSIS_END:
                pending = pending.replace(m, "")
            if pending.strip():
                out.append(("reasoning", pending))
        else:
            for m in self._MARKERS:
                pending = pending.replace(m, "")
            pending = pending.strip()
            if pending:
                out.append(("chunk", self._emit_chunk(pending)))
        return out

