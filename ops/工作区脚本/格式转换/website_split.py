#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P1 抽包：用 AST 把单文件服务端机械切分成 xishu_pipeline/ 包 + 薄入口。

原则：**搬运，不重写**。每个顶层节点的源码逐字保留；只重排位置并补 import。
用法：
  python website_split.py <单体文件> <输出目录>
"""
from __future__ import annotations

import ast
import os
import shutil
import sys

SRC = sys.argv[1] if len(sys.argv) > 1 else r"D:\项目\中节能\0911训练\服务器会话\服务端\xishu_qingyu_qa_线上版.py"
OUT = sys.argv[2] if len(sys.argv) > 2 else r"D:\项目\中节能\0911训练\服务器会话\xishu_site"

# ---- 名字 → 模块 映射表 ----
MAP = {
    # 配置与常量
    "config": ["MODEL_URL", "MODEL_NAME", "DEFAULT_TOP_K",
               "INTENT_ENABLED", "INTENT_BASE_URL", "INTENT_API_KEY", "INTENT_MODEL", "INTENT_TIMEOUT",
               "KG_PATH", "KG_MAX_SUBGRAPH_NODES", "MAX_IMAGE_CHARS"],
    # 提示词（纯文本）
    "prompts": ["INTENT_META_PROMPT", "GENERAL_SYSTEM", "HISTORY_RULE",
                "IMAGE_READ_PROMPT", "IMAGE_RULE",
                "PHOTO_QUERY_SUFFIX", "PHOTO_ROLE_SYSTEM", "PHOTO_JSON_CONTRACT",
                "PHOTO_REPORT_FOOTER", "PHOTO_ITEM_BANK", "PHOTO_VERDICTS"],
    # 意图路由与入口分流
    "route": ["_GENERAL_HINTS", "_PRO_HINTS", "_PRO_PATTERNS", "_ANAPHORA_RE", "_SHORT_Q_RE", "_FILLER_RE",
              "is_public_knowledge", "needs_context", "fallback_standalone", "route_and_enhance",
              "is_direct_chat"],
    # 文本清洗（把模型口吻/标记/乱码清掉）
    "textclean": ["_TAIL_MARKER", "_DISCLAIMER_WORDS", "_INLINE_EVIDENCE", "_TAIL_HOLD_LIMIT", "_SENT_END",
                  "_INLINE_AUDIT", "_INLINE_EVIDENCE2",
                  "strip_audit_words", "clean_general_answer", "GeneralTailGuard",
                  "clean_retrieved_text", "strip_think", "split_public_reasoning"],
    # 知识图谱
    "kg": ["_kg_cache", "load_knowledge_graph", "graph_node_name", "graph_node_json",
           "search_graph", "graph_evidence"],
    # 检索
    "retrieve": ["retriever", "normalize_sources"],
    # 入口规整（12 条入口约束的唯一归属）
    "normalize": ["HybridSearchRequest", "normalize_image", "normalize_history", "_norm_q"],
    # 消息组装
    "compose": ["apply_enhancement", "user_message", "photo_messages"],
    # 图片理解
    "understand": ["read_image", "split_read_result"],
    # 后处理：依据校验 + 报告渲染
    "postprocess": ["photo_render_note", "extract_json_object", "_as_list", "render_photo_report",
                    "_NUM_STD_RE", "_DOC_NAME_RE", "_norm_for_match", "_norm_doc_name",
                    "verify_citations", "citation_warning"],
    # 模型调用
    "llm": ["call_model", "stream_model"],
    # 流式拆分
    "splitter": ["ThinkAnswerSplitter"],
    # 编排（P1 暂不改内部逻辑；P2 再与流式合一）
    "pipeline": ["answer_query"],
    # FastAPI 路由
    "routes": ["app", "health", "hybrid_search", "sse_event", "hybrid_search_stream",
               "hybrid_search_get", "knowledge_graph_stats", "knowledge_graph_search", "index"],
}
NAME2MOD = {n: m for m, names in MAP.items() for n in names}
# 模块内部依赖顺序（被依赖者在前）
ORDER = ["config", "prompts", "route", "textclean", "kg", "retrieve", "normalize", "compose",
         "understand", "postprocess", "llm", "splitter", "pipeline", "routes"]

IMPORT_HEADER = """\
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
"""

# 需要手写特殊头的模块
SPECIAL_HEADER = {
    "retrieve": """\
from __future__ import annotations

import sys
from typing import Any

sys.path.insert(0, "/data/fagui_rag")   # 原单文件里的同一行，位置必须早于 from retriever import
from retriever import Retriever          # noqa: E402
""",
    "config": """\
from __future__ import annotations

import os
from pathlib import Path

# 服务根目录 = xishu_pipeline 的上一级（原单文件里 __file__ 就在服务根，抽包后必须回退一级，
# 否则 KG_PATH 会指向 xishu_pipeline/kg_data 而找不到图谱）
BASE_DIR = Path(__file__).resolve().parent.parent
""",
}

MODULE_DOC = {
    "config": "服务端配置与限制常量。",
    "prompts": "各通路的系统提示词与输出契约（纯文本，无逻辑）。",
    "route": "意图路由：关键词兜底 + 指代消解 + direct_chat / general / rag 判定。",
    "textclean": "文本清洗：模型口吻、标记、免责尾段、PDF 乱码。",
    "kg": "知识图谱加载与子图检索。",
    "retrieve": "向量检索器（单例）与检索结果规整。",
    "normalize": "入口规整与校验：所有入口约束的唯一归属。",
    "compose": "把提示词、证据、图片组装成模型消息。",
    "understand": "图片理解：识图 + 结果拆分。",
    "postprocess": "后处理：依据白名单校验 + 三态报告渲染。",
    "llm": "底层模型调用（流式与非流式）。",
    "splitter": "流式输出拆分器：<think>…</think> → reasoning / answer。",
    "pipeline": "编排层：answer_query（P1 阶段仍与流式实现并存，P2 合一）。",
    "routes": "FastAPI 路由与内嵌前端（P3 阶段把前端外置）。",
}


def node_name(n: ast.AST) -> str | None:
    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return n.name
    if isinstance(n, ast.Assign):
        for t in n.targets:
            if isinstance(t, ast.Name):
                return t.id
    if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
        return n.target.id
    if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call):
        f = n.value.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "app":
            return "__app_expr__"          # app.add_middleware(...)
    return None


def main() -> None:
    src = open(SRC, encoding="utf-8").read()
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)

    buckets: dict[str, list[ast.AST]] = {m: [] for m in ORDER}
    shell_nodes: list[ast.AST] = []
    all_names: set[str] = set()

    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            continue
        if isinstance(n, ast.If):
            shell_nodes.append(n)
            continue
        name = node_name(n)
        if name is None:
            continue
        all_names.add(name)
        mod = NAME2MOD.get(name, "__app_expr__" if name == "__app_expr__" else None)
        if name == "__app_expr__":
            mod = "routes"
        if mod is None:
            print(f"  !! 未映射的顶层节点：{name}（{type(n).__name__} @{n.lineno}）")
            continue
        buckets[mod].append(n)

    missing = [n for n in all_names if n not in NAME2MOD and n != "__app_expr__"]
    assert not missing, f"有名字没被映射：{missing}"

    pkg = os.path.join(OUT, "xishu_pipeline")
    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(pkg, exist_ok=True)

    def seg(n: ast.AST) -> str:
        start = n.lineno
        if getattr(n, "decorator_list", None):
            start = min(start, min(d.lineno for d in n.decorator_list))
        return "".join(lines[start - 1:n.end_lineno])

    # 每个模块用到的**自由**名字（需要从别处 import 的）
    # 注意：必须做作用域感知。曾踩坑——normalize_sources 里的推导式局部变量 `index`
    # 被误判成路由函数 index()，导致 retrieve 反向依赖 routes、形成循环 import。
    def free_names(nodes: list[ast.AST], local: set[str]) -> set[str]:
        used: set[str] = set()
        bound: set[str] = set()
        for n in nodes:
            for sub in ast.walk(n):
                if isinstance(sub, ast.Name):
                    (used if isinstance(sub.ctx, ast.Load) else bound).add(sub.id)
                elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    a = sub.args
                    for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                        bound.add(arg.arg)
                    if a.vararg:
                        bound.add(a.vararg.arg)
                    if a.kwarg:
                        bound.add(a.kwarg.arg)
                elif isinstance(sub, ast.ExceptHandler) and sub.name:
                    bound.add(sub.name)
                elif isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for al in sub.names:
                        bound.add((al.asname or al.name).split(".")[0])
                elif isinstance(sub, ast.Global) or isinstance(sub, ast.Nonlocal):
                    bound.update(sub.names)
        return used - bound - local

    defined_by_mod = {m: {node_name(n) for n in nodes if node_name(n)} for m, nodes in buckets.items()}
    imported_by_mod: dict[str, set[str]] = {}
    for m in ORDER:
        frees = free_names(buckets[m], defined_by_mod[m])
        imps: set[str] = set()
        for other in ORDER:
            if other == m:
                continue
            for nm in frees & defined_by_mod[other]:
                imps.add(f"{other}:{nm}")
        imported_by_mod[m] = imps

    for m in ORDER:
        parts: list[str] = []
        parts.append(f'"""{MODULE_DOC[m]}\n\n（由 website_split.py 从单文件服务端机械切分；逻辑未改。）"""\n')
        parts.append(SPECIAL_HEADER.get(m, IMPORT_HEADER))
        by_mod: dict[str, list[str]] = {}
        for item in sorted(imported_by_mod[m]):
            om, nm = item.split(":", 1)
            by_mod.setdefault(om, []).append(nm)
        if by_mod:
            parts.append("\n# ---- 同包依赖 ----\n")
            for om in ORDER:
                if om not in by_mod:
                    continue
                names = ", ".join(sorted(by_mod[om]))
                parts.append(f"from .{om} import {names}   # noqa: E402\n")
        parts.append("\n\n")
        for n in buckets[m]:
            parts.append(seg(n).rstrip("\n"))
            parts.append("\n\n")
        body = "".join(parts)
        open(os.path.join(pkg, f"{m}.py"), "w", encoding="utf-8", newline="\n").write(body)

    open(os.path.join(pkg, "__init__.py"), "w", encoding="utf-8", newline="\n").write(
        '"""悉数清宇服务端 pipeline 包。"""\n')

    # 薄入口
    shell = ['"""悉数清宇法规问答网页与 FastAPI 服务，监听 8011（薄入口）。',
             '',
             '职责仅三件：把 app 暴露出来、把 __main__ 启动逻辑留下、把 sys.path 设好。',
             '所有业务逻辑在 xishu_pipeline/ 包里。',
             '"""',
             'from __future__ import annotations',
             '',
             'import os',
             'import sys',
             '',
             'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))',
             '',
             'from xishu_pipeline.routes import app   # noqa: E402,F401',
             '',
             '']
    shell.append(seg(shell_nodes[-1]) if shell_nodes else "")
    open(os.path.join(OUT, "xishu_qingyu_qa.py"), "w", encoding="utf-8", newline="\n").write(
        "\n".join(shell))

    print(f"输出目录：{OUT}")
    print(f"  入口 xishu_qingyu_qa.py")
    for m in ORDER:
        p = os.path.join(pkg, f"{m}.py")
        n_lines = sum(1 for _ in open(p, encoding="utf-8"))
        print(f"  xishu_pipeline/{m}.py  {n_lines:5d} 行  顶层符号 {len(defined_by_mod[m]):3d}  "
              f"同包依赖 {len(imported_by_mod[m])}")
    print(f"原文件顶层符号总数：{len(all_names)}；切分后合计：{sum(len(v) for v in defined_by_mod.values())}")


if __name__ == "__main__":
    main()
