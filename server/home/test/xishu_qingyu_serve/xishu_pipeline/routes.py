"""FastAPI 路由与内嵌前端（P3 阶段把前端外置）。

（由 website_split.py 从单文件服务端机械切分；逻辑未改。）"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sys
import time
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               Response, StreamingResponse)
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

# ---- 同包依赖 ----
from .config import (DEFAULT_TOP_K, FRONTEND_PATH, INTENT_KEY_SOURCE,   # noqa: E402
                     KG_MAX_SUBGRAPH_NODES, MD_PREVIEW_MAX, MD_ROOT,
                     MODEL_NAME, PDF_ROOT)
from .errors import (DEFAULT_MESSAGE, ApiError, code_for_status,       # noqa: E402
                     error_body, format_validation_error, new_request_id)
from .kg import (find_entities, graph_suggestions, load_knowledge_graph,   # noqa: E402
                 search_graph)
from .normalize import HybridSearchRequest, normalize_image
from .pipeline import answer_query, run_pipeline
from .resilience import FAQ_CACHE


logger = logging.getLogger("xishu.errors")

app = FastAPI(title="悉数清宇生态环境法规问答", version="1.0.0")

# --------------------------------------------------------------------------
# 统一错误响应（三个处理器）
#
# 改动前本站**一个 exception_handler 都没有**，于是错误响应有四种形状，
# 其中两种会直接打断前端的错误处理（详见 errors.py 的模块说明）：
#   · 422 的 detail 是数组 → 前端 new Error(数组) 显示 [object Object]；
#   · 未捕获异常回**纯文本** "Internal Server Error" → 前端 r.json() 抛 SyntaxError，
#     "报错"变成"界面什么都不发生"，而且服务端**一行日志都没有**。
#
# 这里刻意**不用 @app.middleware**：BaseHTTPMiddleware 包住响应后与
# StreamingResponse 有过兼容问题，而 /hybrid_search/stream 是核心路径。
# request_id 在处理器内部生成即可，不值得为它冒这个风险。
# --------------------------------------------------------------------------

# Starlette 路由层自己抛的 404/405 用的是框架英文原文，直接透出去对用户没意义
_FRAMEWORK_DEFAULT = {"Not Found", "Method Not Allowed", "Internal Server Error",
                      "Bad Request", "Unprocessable Entity"}


@app.exception_handler(StarletteHTTPException)
async def _on_http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTPException（含 ApiError）→ 统一错误体。"""
    code = getattr(exc, "code", None) or code_for_status(exc.status_code)
    if isinstance(exc.detail, str) and exc.detail and exc.detail not in _FRAMEWORK_DEFAULT:
        message = exc.detail
    else:
        message = DEFAULT_MESSAGE.get(code, "请求失败")
    if exc.status_code >= 500:
        logger.warning("HTTP %s %s %s → %s", exc.status_code, request.method,
                       request.url.path, message)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(code, message,
                           detail=getattr(exc, "tech_detail", "") or "",
                           request_id=new_request_id()),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _on_validation_error(request: Request,
                               exc: RequestValidationError) -> JSONResponse:
    """422 校验错误 → 把 detail 数组翻译成一句中文。

    改动前它是 ``{"detail": [{...}, {...}]}``，前端 5 处 ``new Error(d.detail)``
    会把它 ``String()`` 成 ``[object Object]`` / ``[object Object],[object Object]``。
    """
    message, tech = format_validation_error(list(exc.errors()))
    return JSONResponse(
        status_code=422,
        content=error_body("E_VALIDATION", message, detail=tech,
                           request_id=new_request_id()),
    )


@app.exception_handler(Exception)
async def _on_unhandled(request: Request, exc: Exception) -> JSONResponse:
    """未捕获异常 → **回 JSON，并且写日志**。

    改动前这里回的是纯文本 "Internal Server Error"：前端 ``r.json()`` 抛
    SyntaxError（实测 10 处调用方都踩，用户看到的是 JSON 解析器报错原文），
    同时服务端连堆栈都不落盘 —— 线上出错等于无声无息。
    """
    rid = new_request_id()
    logger.exception("未捕获异常 [%s] %s %s", rid, request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body("E_INTERNAL", DEFAULT_MESSAGE["E_INTERNAL"],
                           detail=f"{type(exc).__name__}: {exc}", request_id=rid),
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- 环评报告审核智能体（2026-09-16 新增）----
# 只做"包内新增模块 + 挂载路由"：端口、启动命令、环境变量一律不动
# （launch_xishu_qingyu_qa_8011.sh 的 md5 是冻结的，不得改动）。
from .audit_routes import router as audit_router   # noqa: E402

app.include_router(audit_router)
from .gen_routes import router as gen_router   # noqa: E402
app.include_router(gen_router)

@app.get("/health")
async def health() -> dict[str, str]:
    # intent_key_source 只暴露"密钥来自环境变量还是内置兜底"，不暴露密钥本身
    return {
        "status": "ok",
        "model": MODEL_NAME,
        "intent_key_source": INTENT_KEY_SOURCE,
        "frontend": str(FRONTEND_PATH),
        "pdf_root": str(PDF_ROOT),
        "pdf_root_exists": str(PDF_ROOT.is_dir()),
    }

@app.post("/hybrid_search")
async def hybrid_search(request: HybridSearchRequest) -> dict[str, Any]:
    # 入口校验与编排都在 answer_query 里（与流式端点共用同一条事件流）
    return await answer_query(request)

def sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

@app.post("/hybrid_search/stream")
async def hybrid_search_stream(request: HybridSearchRequest) -> StreamingResponse:
    # 入口校验必须在返回 StreamingResponse 之前做（否则状态码已经发出 200 了）
    query = (request.query or request.question or "").strip()
    image = normalize_image(request.image)
    # 更具体的判断放前面（理由同 pipeline.answer_query）：
    # report=photo 却没带图，必须报错而不是**静默降级** —— run_pipeline 的判断是
    # `if report == "photo" and image:`，没图就直接往下走成普通问答，
    # 用户以为在做现场照片研判，拿到的却是通用答案，且没有任何提示。
    if request.report == "photo" and not image:
        raise ApiError("E_PHOTO_NEEDS_IMAGE",
                       "现场照片专业研判需要上传图片，请带上 image 字段")
    if not query and not image:
        raise ApiError('E_QUERY_EMPTY', "query不能为空")

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

@app.get("/hybrid_search")
async def hybrid_search_get(
    query: str = Query(..., min_length=1),
    top_k: int = Query(DEFAULT_TOP_K, ge=1, le=10),
    max_tokens: int = Query(8192, ge=128, le=16384),
    temperature: float = Query(0.2, ge=0, le=1.5),
    report: str | None = Query(default=None),
) -> dict[str, Any]:
    """GET 版：与 POST 共用同一条事件流，参数已对齐（top_k / max_tokens / temperature）。

    图片不支持走 GET —— URL 长度放不下 base64 图片，硬塞既不可靠也不安全（可能被日志记下来）。
    带图请用 POST /hybrid_search；这里对 report=photo 给明确报错，而不是静默走成别的东西。
    """
    if report == "photo":
        raise ApiError('E_PHOTO_NEEDS_IMAGE', "现场照片专业研判需要上传图片，请用 POST /hybrid_search 并带 image 字段",)
    return await answer_query(HybridSearchRequest(
        query=query.strip(), top_k=top_k, max_tokens=max_tokens, temperature=temperature,
    ))

def _resolve_doc(source: str) -> tuple[str, Path, Path | None]:
    """把索引里的 source（.md 相对路径）解析成 (stem, pdf_路径, md_路径或None)。

    安全约束（三道，与 /doc 一致）：
      1. 只接受 `.md` 结尾 —— 不接受任意路径；
      2. 解析后必须落在对应根目录之内 —— 挡目录穿越（`..`、绝对路径、符号链接）；
      3. 是否存在由调用方判断。
    """
    rel = source.strip().replace("\\", "/").lstrip("/")
    if not rel.lower().endswith(".md"):
        raise ApiError('E_PATH_UNSAFE', "source 必须是索引里的 .md 路径")
    stem = rel[:-3]

    def under(root: Path, suffix: str) -> Path | None:
        target = (root / f"{stem}{suffix}").resolve()
        base = root.resolve()
        if target != base and base not in target.parents:
            raise ApiError('E_PATH_UNSAFE', "路径越界")
        return target if target.is_file() else None

    pdf = under(PDF_ROOT, ".pdf")
    try:
        md = under(MD_ROOT, ".md")
    except ApiError:
        md = None
    return stem, pdf, md


@app.get("/doc")
async def doc(source: str = Query(..., min_length=1, max_length=600)) -> FileResponse:
    """按索引里的 source（.md 相对路径）返回**原文 PDF**，供引用卡片点击打开。

    安全约束（三道）：
      1. 只接受 `.md` 结尾的来源路径 —— 不接受任意路径；
      2. 解析后必须落在 PDF_ROOT 之内 —— 挡目录穿越（`..`、绝对路径、符号链接）；
      3. 只回 `.pdf` 且必须真实存在，否则 404 并说明缺的是哪个文件。
    """
    stem, pdf, md = _resolve_doc(source)
    if pdf is None:
        raise ApiError('E_DOC_NOT_FOUND', f"未找到原文 PDF：{stem}.pdf")
    return FileResponse(
        pdf,
        media_type="application/pdf",
        content_disposition_type="inline",   # 浏览器内直接预览，而不是下载
        filename=pdf.name,
    )


@app.get("/doc/info")
async def doc_info(source: str = Query(..., min_length=1, max_length=600)) -> dict[str, Any]:
    """告诉前端这条引用**能怎么打开**，让它在加载前就知道，而不是把 JSON 错误画进 iframe。

    为什么需要这个接口（2026-09-18 用户反馈）：
    原先前端是直接把 /doc 塞进 <iframe>。资料不存在时服务端返回 404 + JSON，
    **iframe 会把那串 JSON 当文本原样渲染出来** —— 用户看到的是一大坨
    {"ok":false,"code":"E_DOC_NOT_FOUND",...}，而且"正在加载原文 PDF…"还挂在上面。
    iframe 的 onerror 根本抓不到这种"HTTP 200 内容却是错误"的情况，
    所以正确做法是**先问清楚再决定加载什么**。

    返回 has_pdf / has_md 两个布尔值，前端据此三选一：
      · 有 PDF      → 按原样嵌 PDF
      · 只有 .md    → 退回显示文本版全文（环评报告那 592 条就是这种情况）
      · 都没有      → 显示友好说明，不再渲染任何原始错误
    """
    stem, pdf, md = _resolve_doc(source)
    return {
        "ok": True,
        "source": source,
        "stem": stem,
        "has_pdf": pdf is not None,
        "has_md": md is not None,
        "pdf_name": pdf.name if pdf else "",
        "pdf_bytes": pdf.stat().st_size if pdf else 0,
        "md_bytes": md.stat().st_size if md else 0,
    }


@app.get("/doc/info_batch")
async def doc_info_batch(source: list[str] = Query(default=[])) -> dict[str, Any]:
    """批量探测「这几条引用各自能怎么打开」，供引用卡片一次问清。

    为什么要批量（2026-09-19）：单条 /doc/info 也能探，但一条回答有 5–10 条引用，
    逐条探就是 5–10 次往返。这里一次问完，前端在**渲染之前**就知道每条是
    "有 PDF / 只有文本 / 什么都没有"，于是按钮文案说实话，
    也不会再出现「点开才知道 404」——那正是"查看原文 PDF 点不开"的根因。

    设计取舍：这是一次**尽力而为**的探测，所以
      · 非法来源（不是 .md、路径越界）不报错，直接记成"都没有"；
      · 超过 20 条只取前 20 条，不报错。
    引用卡片不该因为一条探测失败就渲染不出来。
    """
    items: dict[str, dict[str, Any]] = {}
    for raw in source[:20]:
        src = (raw or "").strip()
        if not src or len(src) > 600 or src in items:
            continue
        try:
            _, pdf, md = _resolve_doc(src)
            items[src] = {"has_pdf": pdf is not None, "has_md": md is not None}
        except Exception:                      # ApiError 及任何意外，一律当"没有"
            items[src] = {"has_pdf": False, "has_md": False}
    return {"ok": True, "items": items}


@app.get("/doc/text")
async def doc_text(source: str = Query(..., min_length=1, max_length=600)) -> dict[str, Any]:
    """返回原文的**文本版**，供 PDF 缺失时在抽屉里阅读。

    只回 .md 正文（剥掉 YAML 头），不返回 HTML —— 前端用 textContent 渲染，
    不做任何 HTML 注入，从根上避免 XSS。超过 MD_PREVIEW_MAX 会截断并说明。
    """
    stem, pdf, md = _resolve_doc(source)
    if md is None:
        raise ApiError('E_DOC_NOT_FOUND', f"未找到原文文本：{stem}.md")
    raw = md.read_text(encoding="utf-8", errors="replace")

    # 剥掉开头的 YAML front matter（--- ... ---），那是索引元数据，不是正文
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            body = raw[end + 4:].lstrip("\n")

    truncated = len(body) > MD_PREVIEW_MAX
    return {
        "ok": True,
        "source": source,
        "text": body[:MD_PREVIEW_MAX],
        "chars": len(body),
        "truncated": truncated,
        "has_pdf": pdf is not None,
    }



@app.get("/cache/stats")
async def cache_stats() -> dict[str, Any]:
    """常见问题缓存的运行情况。命中率高说明高频问题重复问得多，值得扩内容。"""
    return {"ok": True, **FAQ_CACHE.stats()}


@app.get("/kg/suggest")
async def knowledge_graph_suggest(per_label: int = Query(4, ge=1, le=8)) -> dict[str, Any]:
    """图谱页的「推荐关键词」：按类型给出真实存在的代表实体。

    用户原话：「我也不知道有哪些字段，你让我自己搜索好像不太现实，
    可以放几个推荐的关键词」。所以这里一次给出两样东西：
      · 图谱里**有哪些类型**（各多少个实体）—— 回答"有哪些字段"；
      · 每种类型挑几个**连接最多**的实体当例子 —— 点了保证搜得到。
    """
    return graph_suggestions(per_label)


@app.get("/kg/stats")
async def knowledge_graph_stats() -> dict[str, Any]:
    graph = load_knowledge_graph()
    labels = Counter(node.get("label", "Document") for node in graph["nodes"].values())
    return {
        "available": bool(graph["nodes"]),
        "nodes": len(graph["nodes"]),
        "links": len(graph["edges"]),
        "labels": dict(labels.most_common()),
    }

@app.get("/kg/search")
async def knowledge_graph_search(
    query: str = Query(default="", max_length=200),
    depth: int = Query(default=1, ge=0, le=2),
    limit: int = Query(default=70, ge=10, le=KG_MAX_SUBGRAPH_NODES),
) -> dict[str, Any]:
    return await asyncio.to_thread(search_graph, query, depth, limit)


class KgEntityRequest(BaseModel):
    """正文实体识别的入参。"""
    text: str = Field(default="", max_length=20000)


@app.post("/kg/entities")
async def knowledge_graph_entities(req: KgEntityRequest) -> dict[str, Any]:
    """在正文里找出知识图谱里的实体，供前端把名称变成可点击（第 7 项第一条）。

    用 POST 而不是 GET：回答正文动辄几千字，塞进 query string 会撞 URL 长度上限
    （浏览器约 2KB），中文再乘 3 倍编码，很容易超。同目录的 /kg/search 是 GET
    只因为它搜的是用户敲的几个字。

    找不到实体**不是错误**，回空列表即可 —— 前端不该为这个弹报错。
    """
    entities = await asyncio.to_thread(find_entities, req.text)
    return {"entities": entities, "count": len(entities)}

# ---- 首页静态资源（2026-09-18 重构新增）----------------------------------
# 主页面此前把 CSS/JS 全部内联在 index.html 里（内联占全文 90%、最长行 2623 字符），
# 无法按 Google 风格指南「结构 / 表现 / 行为分离」拆开 —— 根因是**首页没有静态资源路由**，
# 拆出来的文件无处可放。这里补上，与 /gen/static、/audit/static 用同一套白名单做法。
#
# 为什么用白名单而不是通用目录服务：通用目录服务要自己防路径穿越（../、符号链接），
# 白名单从根上就没有这个面。代价是新增文件要在这里登记一行 —— 可以接受。
FRONTEND_DIR = FRONTEND_PATH.parent

# 首页的 ES 模块清单。加一个模块就在这一行加个名字。
# 路由用 {fname:path} 以支持带 / 的键（js/main.js），但**仍是精确匹配白名单** ——
# 精确匹配意味着路径穿越从根上不可能：`../routes.py`、`..%2f..%2froutes.py`
# 都不在表里，直接 404，不需要额外做归一化校验。
_JS_MODULES = ("util", "message", "image", "kg", "views", "store", "ask", "main")

FRONTEND_STATIC: dict[str, str] = {
    "app.css": "text/css; charset=utf-8",
    **{f"js/{m}.js": "application/javascript; charset=utf-8" for m in _JS_MODULES},
}


@app.get("/static/{fname:path}")
async def frontend_static(fname: str) -> Response:
    """首页的 css/js。与 /gen/static、/audit/static 一致：白名单 + no-cache。"""
    media = FRONTEND_STATIC.get(fname)
    if media is None:
        raise ApiError('E_RESOURCE_MISSING', "静态资源不存在")
    path = FRONTEND_DIR / fname
    if not path.is_file():
        raise ApiError('E_RESOURCE_MISSING', f"静态资源缺失：{fname}")
    return Response(content=path.read_text(encoding="utf-8"), media_type=media,
                    headers={"Cache-Control": "no-cache"})


_FRONTEND_CACHE: dict[str, Any] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """首页：前端已外置到 frontend/index.html（按修改时间缓存，改完刷新即可生效）。"""
    try:
        mtime = FRONTEND_PATH.stat().st_mtime
    except OSError as exc:
        raise ApiError('E_FRONTEND_MISSING', f"前端文件缺失：{FRONTEND_PATH}")
    if _FRONTEND_CACHE.get("mtime") != mtime or "html" not in _FRONTEND_CACHE:
        _FRONTEND_CACHE["html"] = FRONTEND_PATH.read_text(encoding="utf-8")
        _FRONTEND_CACHE["mtime"] = mtime
    return _FRONTEND_CACHE["html"]

