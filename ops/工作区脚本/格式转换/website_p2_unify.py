#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P2：流式 / 非流式去重（统一事件流）。

做法（机械变换，不手抄大段代码）：
  1. 把 routes.py 里 hybrid_search_stream 内嵌的 gen() 原样取出、反缩进，
     `yield sse_event("X", Y)` → `yield ("X", Y)`，闭包引用改成显式参数
     → 得到 pipeline.run_pipeline(...)：**唯一的编排实现**（4 条路由只此一份）。
  2. pipeline.answer_query 改为「消费同一个事件流」拼 JSON。
  3. routes.py 的两个端点退化为薄包装（入口校验 + SSE 包装）。
用法：python website_p2_unify.py <站点目录>
"""
from __future__ import annotations

import ast
import os
import re
import sys

SITE = sys.argv[1] if len(sys.argv) > 1 else r"D:\项目\中节能\0911训练\服务器会话\xishu_site"
PKG = os.path.join(SITE, "xishu_pipeline")
ROUTES = os.path.join(PKG, "routes.py")
PIPELINE = os.path.join(PKG, "pipeline.py")

routes_src = open(ROUTES, encoding="utf-8").read()
routes_lines = routes_src.splitlines(keepends=True)


def flatten(lines):
    """把「可能含多行字符串元素的列表」规整成一行一元素。

    踩过的坑：new_post 是**一个含 4 行的元素**，插入后「行号」与「元素索引」不再相等，
    而切片用的是行号 → 偏移 3 行、把旧函数的头几行留在原地，产出语法错误。
    """
    return "".join(lines).splitlines(keepends=True)


def find_fn(fn_name, lines):
    tree = ast.parse("".join(lines))
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == fn_name:
            start = min([n.lineno] + [d.lineno for d in n.decorator_list])
            return start, n.end_lineno, n
    raise SystemExit(f"找不到 {fn_name}")


def replace_fn(lines, fn_name, new_src):
    flat = flatten(lines)
    start, end, _ = find_fn(fn_name, flat)
    return flat[:start - 1] + [new_src] + flat[end:]


# ---------- 1. 取出 gen() 并变换 ----------
_, _, stream_fn = find_fn("hybrid_search_stream", routes_lines)
gen_fn = next((n for n in ast.walk(stream_fn)
               if isinstance(n, ast.AsyncFunctionDef) and n.name == "gen"), None)
assert gen_fn is not None, "没有找到内嵌 gen()"

gen_lines = routes_lines[gen_fn.lineno - 1: gen_fn.end_lineno]
body = "".join(ln[4:] if ln.startswith("    ") else ln for ln in gen_lines[1:])

body = body.replace("yield sse_event(", "yield (")          # 事件流化
for a, b in [("request.report", "report"), ("request.history or []", "history or []"),
             ("request.top_k", "top_k"), ("request.max_tokens", "max_tokens"),
             ("request.temperature", "temperature")]:
    body = body.replace(a, b)

n_calls = body.count("stream_model(")
assert n_calls == 4, f"stream_model 调用次数异常：{n_calls}"
# 每次流式调用带上 usage 收集器（photo 分支的温度写死 0.0，要一并覆盖）
body, n1 = re.subn(r"((?:temperature|0\.0),)\n(\s*)\):",
                   r"\1\n\2    usage_out=usage_box,\n\2):", body)
assert n1 == n_calls, f"usage_out 注入 {n1}/{n_calls}"
# done 事件里带上 usage（与改动前的非流式响应保持一致）
body, n2 = re.subn(r'(\s*)"model": MODEL_NAME,\n',
                   r'\1"model": MODEL_NAME,\n\1"usage": usage_box.get("usage", {}),\n', body)
assert n2 == 4, f"done 事件 usage 注入 {n2}/4"

header = '''"""编排层：唯一的事件流实现 + 非流式收集器。

**P2 重构的核心设计**：把「事件流」作为服务端唯一的内部输出格式。
  · POST /hybrid_search/stream → 把事件流转成 SSE（前端实际走的）
  · POST /hybrid_search        → 把同一个事件流收集成 JSON
  · GET  /hybrid_search        → 同上
4 条路由（chat / photo / general / rag）**只实现一次**，不再有两份近似重复的编排
（P2 之前改一个功能要在两个地方各改一遍，且两边已经出现行为漂移）。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncIterator

from fastapi import HTTPException

from .config import MODEL_NAME
from .prompts import GENERAL_SYSTEM, HISTORY_RULE, IMAGE_RULE, PHOTO_QUERY_SUFFIX
from .route import fallback_standalone, is_direct_chat, route_and_enhance
from .textclean import GeneralTailGuard
from .kg import graph_evidence
from .retrieve import normalize_sources, retriever
from .normalize import normalize_history, normalize_image
from .compose import apply_enhancement, photo_messages, user_message
from .postprocess import (citation_warning, extract_json_object, photo_render_note,
                          render_photo_report, verify_citations)
from .understand import read_image, split_read_result
from .llm import stream_model
from .splitter import ThinkAnswerSplitter


'''

run_pipeline = (
    "async def run_pipeline(\n"
    "    *,\n"
    "    query: str,\n"
    "    image: str | None,\n"
    "    history: list[dict[str, str]] | None = None,\n"
    "    top_k: int = 5,\n"
    "    max_tokens: int = 8192,\n"
    "    temperature: float = 0.2,\n"
    "    report: str | None = None,\n"
    ") -> AsyncIterator[tuple[str, Any]]:\n"
    '    """唯一的编排实现：产出 (事件名, 数据)。\n\n'
    "    事件名：status / vision / meta / reasoning / chunk / error / done。\n"
    "    第 4 条 done 事件里的 usage 供非流式端点拼响应使用。\n"
    '    """\n'
    "    started = time.perf_counter()\n"
    "    usage_box: dict[str, Any] = {}\n"
    + body
)

drain = '''

async def answer_query(request: Any) -> dict[str, Any]:
    """非流式：消费**同一个**事件流，拼出 JSON 响应。

    与流式端点共用 run_pipeline，因此两条通路的路由、检索、提示词、后处理
    永远一致——这正是 P2 之前最容易漂移的地方。
    """
    query = (request.query or request.question or "").strip()
    image = normalize_image(request.image)

    route = ""
    sources: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    answer_parts: list[str] = []
    image_note = ""
    done: dict[str, Any] = {}
    error: str | None = None

    async for event, data in run_pipeline(
        query=query,
        image=image,
        history=request.history,
        top_k=request.top_k,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        report=request.report,
    ):
        if event == "reasoning":
            reasoning_parts.append(data if isinstance(data, str) else "")
        elif event == "chunk":
            answer_parts.append(data if isinstance(data, str) else "")
        elif event == "vision":
            image_note = (data or {}).get("text", "") or image_note
        elif event == "meta":
            route = (data or {}).get("route", route) or route
            if (data or {}).get("sources"):
                sources = data["sources"]
        elif event == "done":
            done = data or {}
            route = done.get("route", route) or route
            if done.get("sources"):
                sources = done["sources"]
        elif event == "error":
            error = data if isinstance(data, str) else str(data)

    answer = "".join(answer_parts)
    if error and not answer.strip():
        # 一个字的答案都没产出：按服务异常返回（与改动前的非流式行为一致）
        raise HTTPException(status_code=502, detail=error)

    result: dict[str, Any] = {
        "query": done.get("query_used") or query,
        "route": route,
        "image_note": image_note,
        "history_turns_used": done.get("history_turns_used", 0),
        "answer": answer,
        "reasoning": "".join(reasoning_parts),
        "sources": sources,
        "model": MODEL_NAME,
        "usage": done.get("usage", {}),
        "latency_s": done.get("latency_s"),
    }
    for extra in ("missing_citations", "render_stats", "render_note"):
        if extra in done:
            result[extra] = done[extra]
    if error:
        result["error"] = error
    return result
'''

open(PIPELINE, "w", encoding="utf-8", newline="\n").write(header + run_pipeline + "\n" + drain)

# ---------- 3. routes.py：端点退化为薄包装 ----------
new_post = '''@app.post("/hybrid_search")
async def hybrid_search(request: HybridSearchRequest) -> dict[str, Any]:
    # 入口校验与编排都在 answer_query 里（与流式端点共用同一条事件流）
    return await answer_query(request)
'''

new_stream = '''@app.post("/hybrid_search/stream")
async def hybrid_search_stream(request: HybridSearchRequest) -> StreamingResponse:
    # 入口校验必须在返回 StreamingResponse 之前做（否则状态码已经发出 200 了）
    query = (request.query or request.question or "").strip()
    image = normalize_image(request.image)
    if not query and not image:
        raise HTTPException(status_code=400, detail="query不能为空")

    async def gen():
        async for event, data in run_pipeline(
            query=query,
            image=image,
            history=request.history,
            top_k=request.top_k,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            report=request.report,
        ):
            yield sse_event(event, data)

    return StreamingResponse(gen(), media_type="text/event-stream")
'''

new_get = '''@app.get("/hybrid_search")
async def hybrid_search_get(
    query: str = Query(..., min_length=1),
    top_k: int = Query(DEFAULT_TOP_K, ge=1, le=10),
) -> dict[str, Any]:
    return await answer_query(HybridSearchRequest(query=query.strip(), top_k=top_k))
'''

routes_lines = replace_fn(routes_lines, "hybrid_search", new_post)
routes_lines = replace_fn(routes_lines, "hybrid_search_stream", new_stream)
routes_lines = flatten(routes_lines)          # 同样必须先规整，否则行号≠索引
s, e, _ = find_fn("hybrid_search_get", routes_lines)
routes_lines = routes_lines[:s - 1] + [new_get] + routes_lines[e:]
out = "".join(routes_lines)

out = re.sub(r"from \.pipeline import answer_query\b[^\n]*\n",
             "from .pipeline import answer_query, run_pipeline   # noqa: E402\n", out)
if "from .pipeline import answer_query, run_pipeline" not in out:
    out = out.replace("# ---- 同包依赖 ----\n",
                      "# ---- 同包依赖 ----\n"
                      "from .pipeline import answer_query, run_pipeline   # noqa: E402\n", 1)
open(ROUTES, "w", encoding="utf-8", newline="\n").write(out)


def prune_imports(path):
    """把抽包时自动补上的同包 import 里**已经用不到**的名字删掉。

    编排搬走以后，routes.py 会留下一堆用不上的 import（P1 是按"用到就导入"自动生成的）。
    不清理的话，"routes.py 还有没有第二份实现"这类结构断言就没法用，也违背这次的整洁目标。
    """
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    local = set()
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            local.add(n.name)
        elif isinstance(n, ast.Assign):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    local.add(t.id)
    used, bound = set(), set(local)
    for n in ast.walk(tree):
        if isinstance(n, ast.Name):
            (used if isinstance(n.ctx, ast.Load) else bound).add(n.id)
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            a = n.args
            for arg in list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs):
                bound.add(arg.arg)
            if a.vararg:
                bound.add(a.vararg.arg)
            if a.kwarg:
                bound.add(a.kwarg.arg)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            bound.add(n.name)
        # 注意：**不要把 import 语句本身算进 bound**。第一版算了，结果每个跨模块导入
        # 都把自己"绑定"了，于是全部被判定为"不需要"而删掉（DEFAULT_TOP_K 直接 NameError）。
    needed = used - bound
    kept, dropped = [], []
    for ln in open(path, encoding="utf-8").read().splitlines(keepends=True):
        m = re.match(r"from \.(\w+) import (.+?)(\s+#.*)?\n?$", ln)
        if not m:
            kept.append(ln)
            continue
        mod_name, names = m.group(1), [x.strip() for x in m.group(2).split(",")]
        keep = [x for x in names if x in needed]
        dropped += [x for x in names if x not in needed]
        if keep:
            kept.append(f"from .{mod_name} import {', '.join(keep)}\n")
    open(path, "w", encoding="utf-8", newline="\n").write("".join(kept))
    return dropped


dropped = prune_imports(ROUTES)

print(f"run_pipeline 体 {body.count(chr(10))} 行；usage_out 注入 {n1} 处；done.usage 注入 {n2} 处")
print(f"routes.py 清理掉无用 import：{len(dropped)} 个 -> {dropped}")
print("已写入:", PIPELINE)
print("已改写:", ROUTES)
