"""编排层：唯一的事件流实现 + 非流式收集器。

**P2 重构的核心设计**：把「事件流」作为服务端唯一的内部输出格式。
  · POST /hybrid_search/stream → 把事件流转成 SSE（前端实际走的）
  · POST /hybrid_search        → 把同一个事件流收集成 JSON
  · GET  /hybrid_search        → 同上
4 条路由（chat / photo / general / rag）**只实现一次**，不再有两份近似重复的编排
（P2 之前改一个功能要在两个地方各改一遍，且两边已经出现行为漂移）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, AsyncIterator

from fastapi import HTTPException

from .config import MODEL_NAME
from .errors import ApiError
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
from .resilience import (DEGRADED_CHAT_NOTE, FAQ_CACHE, PHOTO_DEGRADED_NOTE,
                         retrieval_failed_note, sources_digest, stream_with_retry)
from .splitter import ThinkAnswerSplitter

# 降级与重试都要留痕：界面上只显示友好文案，真实原因必须能在服务端日志里查到。
# （用户的要求：界面说"当前网络繁忙"，实际错误进日志/控制台。）
logger = logging.getLogger("xishu.pipeline")


def source_block(s: dict[str, Any]) -> str:
    """把一条检索命中拼成给模型的资料块，**并把索引元数据带上**。

    为什么必须带（2026-09-22 用户反馈 B1/B2 的根因）：
    原先这里是 `[{index}] 《{title}》\\n{text}` —— **状态字段完全没进提示词**。
    于是索引里明明写着「已废止」、界面引用卡片上也显示「已废止」，
    模型却只看得到正文里那句「本法自 2020 年 9 月 1 日起施行」，
    得出的结论就成了「目前仍为有效法律」，还反过来写"未见废止或失效声明"。
    实测（`_脚本代码/站点全量测试/复测5个错例_B1B5.py`）：
    改状态标记之后，固废法/环评法自身的块确实已是「已废止」，
    但**答案没变** —— 因为这一行没带状态。

    现在把「标准号／材料类型／时效状态」放进标题后的括号里，
    配合 system 里那条"已废止只能作历史参考"的规则，模型才有判断依据。
    元数据一律取自索引（不做推断）；没有的字段就不写，不编。
    """
    head = f"[{s.get('index')}] 《{s.get('title') or ''}》"
    meta = []
    if s.get("standard_id"):
        meta.append(str(s["standard_id"]))
    if s.get("doc_type"):
        meta.append(str(s["doc_type"]))
    if s.get("issuer"):
        meta.append("发布：" + str(s["issuer"]))
    if s.get("region"):
        meta.append(str(s["region"]))
    st = str(s.get("status") or "").strip()
    if st:
        # 带上「为什么」：实测只给一个"已废止"的标记，模型会不信
        # （环评法那次答成"元数据标注为已废止，但与正文记载不一致，可能是录入错误"），
        # 加上依据之后它才有得比。status_note 来自 bundle 的 front matter，不是这里编的。
        note = str(s.get("status_note") or "").strip()
        meta.append("时效状态：" + st + (" —— " + note if note else ""))
    if meta:
        head += "（" + "，".join(meta) + "）"
    return head + "\n" + str(s.get("text") or "")


async def _model_stream(
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    usage_box: dict[str, Any],
    *,
    response_format: dict[str, Any] | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """带重试的模型流，把"正在重新处理"作为 status 事件报给前端。

    产出 ``("status", {...})`` 或 ``("chunk", 文本)``。
    调用方对 chunk 走 splitter，对 status 直接转发。

    为什么重试要在这里插一条 status：用户看到的是"当前网络繁忙，正在重新处理…"
    而不是界面卡住不动。这正是用户要求的文案。
    重试成功后补一条 done 把这一步收尾；彻底失败时由前端的
    closeRunningSteps 兜底收尾（见 ask.js）。
    """
    retrying = False
    async for kind, payload in stream_with_retry(
        stream_model, messages, max_tokens, temperature,
        usage_out=usage_box, response_format=response_format,
    ):
        if kind == "retry":
            retrying = True
            yield ("status", {
                "stage": "retry",
                "message": "当前网络繁忙，正在重新处理…",
                "state": "run",
                "detail": "第 %d 次重试" % payload,
            })
            continue
        if retrying:
            retrying = False
            yield ("status", {"stage": "retry", "message": "已重新连接", "state": "done"})
        yield ("chunk", payload)


async def run_pipeline(
    *,
    query: str,
    image: str | None,
    history: list[dict[str, str]] | None = None,
    top_k: int = 5,
    max_tokens: int = 8192,
    temperature: float = 0.2,
    report: str | None = None,
) -> AsyncIterator[tuple[str, Any]]:
    """唯一的编排实现：产出 (事件名, 数据)。

    事件名：status / vision / meta / reasoning / chunk / error / done。
    第 4 条 done 事件里的 usage 供非流式端点拼响应使用。
    """
    started = time.perf_counter()
    usage_box: dict[str, Any] = {}
    started = time.perf_counter()
    recognized = ""
    question = query
    vision_task = None
    if image:
        # 步骤事件约定（前端按这个渲染"处理过程"）：
        #   {"stage": 步骤键, "message": 给人看的短句, "state": "run"|"done",
        #    "detail": 完成时的补充（耗时/条数，可省）, "progress": 进行中的字数（可省）}
        # 每个长耗时动作都要发 run 和 done 一对，否则前端只能一直转圈。
        yield ("status", {"stage": "vision", "message": "读取图片", "state": "run"})
        if not query:
            # 只发图不打字：必须先把图读成文字，才能作为路由与检索的问题
            _t = time.perf_counter()
            try:
                read_text = await read_image(image)
            except Exception as exc:
                yield ("error", {"code": "E_VISION_FAILED", "message": f"图片识别失败：{exc}"})
                return
            if not read_text:
                yield ("error", {"code": "E_VISION_FAILED",
                                 "message": "图片内容无法识别，请换一张更清晰的图片"})
                return
            question, recognized = split_read_result(read_text)
            yield ("status", {"stage": "vision", "message": "图片已识别", "state": "done",
                              "detail": "%d 字 · %.1fs" % (len(recognized), time.perf_counter() - _t)})
            yield ("vision", {"text": recognized})
        else:
            # 图文同问：识图与检索并行，不额外增加等待时间
            vision_task = asyncio.create_task(read_image(image))
    effective_query = question or recognized or "请说明这张图片的内容"

    chat_history = normalize_history(history or [], effective_query)
    top_k = top_k
    max_tokens = max_tokens
    temperature = temperature

    # ===== 高频常见问题缓存 =====
    #
    # 放在所有分支之前，命中就完全不调模型。
    # key_for 遇到"带图片"或"带多轮历史"会返回 None —— 那类提问高度依赖上下文，
    # 缓存会让答案串味（之前"发完图之后问什么都答图片"的 bug 就是这么来的）。
    cache_key = FAQ_CACHE.key_for(effective_query, has_image=bool(image), history=chat_history)
    cached = FAQ_CACHE.get(cache_key)
    if cached is not None:
        yield ("status", {"stage": "cache", "message": "命中常见问题缓存", "state": "run"})
        yield ("meta", {"route": cached["route"], "sources": cached.get("sources") or [],
                        "enhanced": False})
        if cached.get("reasoning"):
            yield ("reasoning", cached["reasoning"])
        if cached.get("content"):
            yield ("chunk", cached["content"])
        yield ("status", {"stage": "cache", "message": "已直接返回缓存答案", "state": "done"})
        yield ("done", {
            "route": cached["route"],
            "sources": cached.get("sources") or [],
            "history_turns_used": 0,
            "latency_s": round(time.perf_counter() - started, 3),
            "model": "cache",
            "cached": True,
            # 回放原始 usage，保证命中缓存与未命中时响应形状一致
            "usage": cached.get("usage") or {},
        })
        return

    # 生成过程中的正文/推理累加，成功结束后用于写入缓存。
    # 放在这里而不是各分支各自维护：三个分支（direct/general/rag）都要用。
    #
    # ★ 必须连 reasoning 和 usage 一起缓存，不能只存 content。
    # 为什么：非流式端点（POST /hybrid_search）是把同一个事件流收集成 JSON。
    # 如果缓存命中时只回正文、没有推理和 usage，那么同一个问题
    # 「先流式问一次、再非流式问一次」会得到**形状不同**的两个响应 ——
    # 回归基线里的 11b「流式/非流式一致性」正是这么抓出来的。
    answer_parts: list[str] = []
    reasoning_parts: list[str] = []

    # ===== 现场照片专业研判：独立通路，不走意图路由（判定要有依据，必须检索）=====
    if report == "photo" and image:
        image_detail = ""
        if vision_task is not None:
            _t = time.perf_counter()
            try:
                read_text = await vision_task
            except Exception:
                read_text = ""
            if read_text:
                _, image_detail = split_read_result(read_text)
                yield ("status", {"stage": "vision", "message": "图片已识别", "state": "done",
                                  "detail": "%d 字 · %.1fs" % (len(image_detail), time.perf_counter() - _t)})
                if image_detail:
                    yield ("vision", {"text": image_detail})
        # 检索是照片通路里第二段静默：先报"在检索"，回来报条数
        yield ("status", {"stage": "retrieve", "message": "检索判据与标准", "state": "run"})
        _t = time.perf_counter()
        try:
            found = await asyncio.to_thread(
                retriever.retrieve, f"{effective_query} {PHOTO_QUERY_SUFFIX}", 20, top_k
            )
            sources = normalize_sources(found)
        except Exception:
            sources = []
        yield ("status", {"stage": "retrieve", "message": "已找到依据", "state": "done",
                          "detail": "%d 条 · %.1fs" % (len(sources), time.perf_counter() - _t)})
        yield ("meta", {"route": "photo", "sources": sources, "enhanced": False})
        context = (
            "\n\n".join(source_block(s) for s in sources)
            if sources else "未检索到可用资料。"
        )
        yield ("status", {"stage": "generate", "message": "生成专业研判", "state": "run"})
        raw = ""
        obj = None
        retried = False
        _t = time.perf_counter()
        for attempt in (1, 2):
            if attempt == 2:
                # 第一次没解析出 JSON，要整段重来 —— 这又是一次长等待，必须说出来，
                # 否则用户会以为程序卡死了。
                yield ("status", {"stage": "generate", "message": "结果不是结构化格式，重新生成",
                                  "state": "run"})
            collected: list[str] = []
            n_chars = 0
            _tick = 0.0
            try:
                async for kind, payload in _model_stream(
                    photo_messages(context, image, image_detail, query, retry=(attempt == 2)),
                    max_tokens,
                    0.0,
                    usage_box,
                    # 照片研判必须出 JSON：契约写在 system 里，实测模型会"读懂却用散文复述"
                    # （输出里一个 `{` 都没有）→ extract_json_object 返回 None → 结构化渲染失效。
                    # 加这一个参数后实测首次即通过；普通问答通路不传，行为与改动前一致。
                    response_format={"type": "json_object"},
                ):
                    if kind == "status":
                        # 连接级重试（"当前网络繁忙，正在重新处理…"）直接转发给前端
                        yield ("status", payload)
                        continue
                    collected.append(payload)
                    n_chars += len(payload)
                    # 整段 JSON 要攒完才能渲染成报告，中途确实没有正文可发。
                    # 但一句不吭会被当成卡死，所以按时间节流报进度（约 0.8s 一次，
                    # 不是每个 chunk 都发 —— 那会把 SSE 冲爆，反而更慢）。
                    _now = time.perf_counter()
                    if _now - _tick >= 0.8:
                        _tick = _now
                        yield ("status", {"stage": "generate", "message": "生成专业研判",
                                          "state": "run", "progress": n_chars})
            except ApiError as exc:
                logger.warning("photo 研判生成失败（重试后仍失败）：%s",
                               exc.tech_detail or exc.message)
                yield ("status", {"stage": "generate", "message": "已给出提示", "state": "done"})
                yield ("chunk", PHOTO_DEGRADED_NOTE)
                yield ("done", {
                    "route": "photo",
                    "sources": sources,
                    "history_turns_used": len(chat_history),
                    "latency_s": round(time.perf_counter() - started, 3),
                    "model": MODEL_NAME,
                    "degraded": True,
                    "usage": usage_box.get("usage", {}),
                })
                return
            raw = "".join(collected)
            obj = extract_json_object(raw)
            if obj is not None:
                break
            retried = True
        yield ("status", {"stage": "generate", "message": "研判内容已生成", "state": "done",
                          "detail": "%d 字 · %.1fs" % (len(raw), time.perf_counter() - _t)})
        yield ("status", {"stage": "render", "message": "渲染研判报告", "state": "run"})
        render_stats = {"dropped_items": 0, "coerced_verdicts": 0, "coerced_stance": 0}
        render_note = ""
        if obj:
            report, render_stats = render_photo_report(obj)
            report += photo_render_note(render_stats, retried)
        else:
            render_note = "json_parse_failed"
            report = (
                "⚠️ 本次未能解析出结构化研判结果（已自动纠错重试一次），"
                "以下为模型原文，未经系统渲染，请谨慎使用。\n\n"
                + raw.split("</think>")[-1].strip()
            )
        yield ("status", {"stage": "render", "message": "研判报告已生成", "state": "done",
                          "detail": "%d 字 · 合计 %.1fs" % (len(report), time.perf_counter() - _t)})
        # 报告由代码渲染，无法逐字流式：先把推理过程发出去，再一次性发正文
        for typ, text in ThinkAnswerSplitter().feed(raw):
            if typ != "chunk":
                yield (typ, text)
        yield ("chunk", report)
        # 依据白名单校验：不依赖模型自觉
        yield ("status", {"stage": "verify", "message": "核验引用依据", "state": "run"})
        missing = verify_citations(report, sources)
        warn = citation_warning(missing)
        yield ("status", {"stage": "verify",
                          "message": "引用依据核验完成" if not missing
                                     else "%d 条引用未对上原文" % len(missing),
                          "state": "done"})
        if warn:
            yield ("chunk", warn)
        yield ("done", {
            "route": "photo",
            "sources": sources,
            "missing_citations": missing,
            "render_stats": render_stats,
            "render_note": render_note,
            "history_turns_used": len(chat_history),
            "latency_s": round(time.perf_counter() - started, 3),
            "model": MODEL_NAME,

            "usage": usage_box.get("usage", {}),
        })
        return

    if is_direct_chat(effective_query) and not image:
        yield ("status", {"stage": "generate", "message": "生成中…", "state": "run"})
        system = (
            "你是中节能研发的悉数清宇大模型。"
            "对问候、身份、自我介绍和功能类问题直接、简洁、自然地回答，"
            "不要声称查询了法规资料，不要展开法律分析。"
            "必须使用以下格式：【分析过程】用一句话说明用户意图；【回答】给出简短自然的回答。"
            + HISTORY_RULE
        )
        splitter = ThinkAnswerSplitter()
        try:
            async for kind, payload in _model_stream(
                [{"role": "system", "content": system}] + chat_history + [user_message(effective_query, image)],
                max_tokens,
                temperature,
                usage_box,
            ):
                if kind == "status":
                    yield ("status", payload)
                    continue
                for typ, text in splitter.feed(payload):
                    if typ == "chunk":
                        answer_parts.append(text)
                    elif typ == "reasoning":
                        reasoning_parts.append(text)
                    yield (typ, text)
            for typ, text in splitter.flush():
                if typ == "chunk":
                    answer_parts.append(text)
                elif typ == "reasoning":
                    reasoning_parts.append(text)
                yield (typ, text)
        except ApiError as exc:
            # 直接对话这条通路没有资料可降级，只能给一句友好的话。
            # 真实原因进服务端日志，不进正文 —— 用户看到的是"出了点问题，重试通常能好"。
            logger.warning("direct_chat 生成失败（重试后仍失败）：%s", exc.tech_detail or exc.message)
            yield ("status", {"stage": "generate", "message": "已给出提示", "state": "done"})
            yield ("chunk", DEGRADED_CHAT_NOTE)
            yield ("done", {
                "route": "direct_chat",
                "sources": [],
                "history_turns_used": len(chat_history),
                "latency_s": round(time.perf_counter() - started, 3),
                "model": MODEL_NAME,
                "degraded": True,
                "usage": usage_box.get("usage", {}),
            })
            return
        FAQ_CACHE.put(cache_key, {"content": "".join(answer_parts), "sources": [],
                                  "route": "direct_chat",
                                  "reasoning": "".join(reasoning_parts),
                                  "usage": usage_box.get("usage", {})})
        yield ("status", {"stage": "generate", "message": "回答已生成", "state": "done"})
        yield ("done", {
            "route": "direct_chat",
            "sources": [],
            "history_turns_used": len(chat_history),
            "latency_s": round(time.perf_counter() - started, 3),
            "model": MODEL_NAME,

            "usage": usage_box.get("usage", {}),
        })
        return

    # 意图路由与检索并行：路由结果决定是否使用检索到的资料
    yield ("status", {"stage": "intent", "message": "识别意图…", "state": "run"})

    # 先用启发式判断当前问题是否需要上文，抢出检索时间；
    # 若路由环节把追问改写成独立问题，再用改写结果重检。
    guess = fallback_standalone(effective_query, chat_history)

    async def _retrieve(text: str):
        try:
            found = await asyncio.to_thread(retriever.retrieve, text, 20, top_k)
            return normalize_sources(found), None
        except Exception as exc:  # 科普通道不需要检索，不能因此报错
            return None, exc

    retrieval_task = asyncio.create_task(_retrieve(guess))
    route, enhancement, standalone = await route_and_enhance(effective_query, chat_history)
    if standalone and standalone != guess:
        retrieval_task.cancel()
        retrieval_task = asyncio.create_task(_retrieve(standalone))
    # 这一步要显式收尾：前端把 status(run) 画成转圈的行，没有配对的 done 就一直转。
    # 原先 intent 只发 run 从不发 done，普通问答的时间线第一步永远停不下来。
    yield ("status", {"stage": "intent", "message": "意图已识别", "state": "done",
                      "detail": "科普问答" if route == "general" else "法规检索问答"})

    # 图文同问：收拢并行的识图结果，展示给用户核对，并作为补充材料进提示词
    image_detail = ""
    if vision_task is not None:
        # 识图虽然与检索并行，但收拢时可能还没跑完 —— 这一步也要说清楚在等什么，
        # 否则界面上只有"识别意图…"一直转，用户不知道卡在哪。
        if not vision_task.done():
            yield ("status", {"stage": "vision", "message": "等待图片识别完成", "state": "run"})
        _t = time.perf_counter()
        try:
            read_text = await vision_task
        except Exception:
            read_text = ""
        if read_text:
            _, image_detail = split_read_result(read_text)
            yield ("status", {"stage": "vision", "message": "图片已识别", "state": "done",
                              "detail": "%d 字 · %.1fs" % (len(image_detail), time.perf_counter() - _t)})
            if image_detail:
                yield ("vision", {"text": image_detail})

    # 公众日常/科普：不检索、不引用资料，用通俗讲法直接回答
    if route == "general":
        retrieval_task.cancel()
        yield ("status", {"stage": "generate", "message": "生成中…", "state": "run"})
        yield ("meta", {"route": "general", "sources": [], "enhanced": False})
        splitter = ThinkAnswerSplitter()
        guard = GeneralTailGuard()
        general_system = GENERAL_SYSTEM + (IMAGE_RULE if image else "") + HISTORY_RULE
        general_user = effective_query + (
            f"\n\n【图片识别内容】\n{image_detail}" if image_detail else ""
        )
        try:
            async for kind, payload in _model_stream(
                [{"role": "system", "content": general_system}]
                + chat_history
                + [user_message(general_user, image)],
                max_tokens,
                temperature,
                usage_box,
            ):
                if kind == "status":
                    yield ("status", payload)
                    continue
                for typ, text in splitter.feed(payload):
                    if typ == "chunk":
                        text = guard.feed(text)
                        if not text:
                            continue
                        answer_parts.append(text)
                    elif typ == "reasoning":
                        reasoning_parts.append(text)
                    yield (typ, text)
            for typ, text in splitter.flush():
                if typ == "chunk":
                    text = guard.feed(text)
                    if text:
                        answer_parts.append(text)
                elif typ == "reasoning":
                    reasoning_parts.append(text)
                if text:
                    yield (typ, text)
            held = guard.flush()
            if held:
                answer_parts.append(held)
                yield ("chunk", held)
        except ApiError as exc:
            logger.warning("general 生成失败（重试后仍失败）：%s", exc.tech_detail or exc.message)
            yield ("status", {"stage": "generate", "message": "已给出提示", "state": "done"})
            yield ("chunk", DEGRADED_CHAT_NOTE)
            yield ("done", {
                "route": "general",
                "sources": [],
                "history_turns_used": len(chat_history),
                "latency_s": round(time.perf_counter() - started, 3),
                "model": MODEL_NAME,
                "degraded": True,
                "usage": usage_box.get("usage", {}),
            })
            return
        FAQ_CACHE.put(cache_key, {"content": "".join(answer_parts), "sources": [],
                                  "route": "general",
                                  "reasoning": "".join(reasoning_parts),
                                  "usage": usage_box.get("usage", {})})
        yield ("status", {"stage": "generate", "message": "回答已生成", "state": "done"})
        yield ("done", {
            "route": "general",
            "sources": [],
            "history_turns_used": len(chat_history),
            "latency_s": round(time.perf_counter() - started, 3),
            "model": MODEL_NAME,

            "usage": usage_box.get("usage", {}),
        })
        return

    yield ("status", {"stage": "retrieve", "message": "检索法规资料", "state": "run"})
    hits, retrieval_error = await retrieval_task
    if retrieval_error is not None:
        yield ("error", {"code": "E_RETRIEVE_FAILED", "message": f"检索服务异常：{retrieval_error}"})
        return
    sources = hits
    for evidence in graph_evidence(effective_query):
        sources.append({
            "index": len(sources) + 1,
            "title": evidence["title"],
            "source": evidence["source"],
            "text": evidence["text"],
            "rerank_score": None,
            "vector_score": None,
        })
    yield ("status", {"stage": "retrieve", "message": "已找到资料", "state": "done",
                      "detail": "%d 条" % len(sources)})
    yield ("status", {"stage": "generate", "message": "生成中…", "state": "run"})
    yield ("meta", {"route": "rag", "sources": sources, "enhanced": bool(enhancement)})
    if not sources:
        context = "未检索到可用资料。"
    else:
        context = "\n\n".join(source_block(s) for s in sources)
    base_system = (
        "你是悉数清宇大模型，负责生态环境法律法规、标准规范和监管执法问答。"
        "请先给出简明、可核查的分析，再给出结论。只使用所给参考资料中的事实、规则、数值和程序；"
        "每项实质性结论用[编号]标注依据。资料不足时明确指出缺少什么，不得用常识补全。"
        "资料标题后括号里是**索引元数据**（标准号／材料类型／时效状态），是判断"
        "「这个法/标准现在还能不能用」的直接依据：标注「已废止」「已失效」的材料只能作历史参考，"
        "回答「是否仍适用／是否有效」时必须先说明其已废止、并指出应改用哪一部现行依据，"
        "**不得**表述为「目前仍有效」「继续适用」；只有标「现行」的才可作为现行依据。"
        "元数据由语料库维护、部分条目还给了废止依据（破折号之后那句），"
        "其效力高于环评报告等二手引用 —— **不得**因为某份报告仍在引用它，"
        "或自己「没看到废止公告」，就反推它仍然有效、或怀疑元数据标错了。"
        "若确有冲突且你无法解释，就照元数据说，并把冲突点写出来请人工复核。"
        "判断「标准怎么分级、在哪采样、限值多少」这类**标准本体问题**时，"
        "只认该标准的原文块（标题就是标准本身、且号对得上）；"
        "环评报告里写的「执行某标准三级标准」「排入园区污水管网」属于**报告转述**，"
        "只能说明某个项目怎么执行，**不能**用来反推标准本身的分类或采样口规定。"
        "若标准原文里没有出现被问的限值或条款（常见于限值表是图片、没进语料），"
        "就明说「标准原文未覆盖该条」，**不要**用报告的转述补一个数值或档级顶上。"
        "必须使用以下格式：【分析过程】给出证据与结论之间简明、公开、可核验的推导摘要；"
        "【回答】直接回答问题。分析摘要不得包含证据之外的猜测。"
        "回答长度与问题复杂度匹配：问题简单就直接给结论，不要整段照抄法条原文，"
        "只引用与结论直接相关的内容；涉及案件分析或多问句的，要逐项回应，"
        "把每个要件的证据与结论都讲清楚，不要压缩。"
        + HISTORY_RULE
    )
    system = apply_enhancement(base_system, enhancement)
    if image:
        system += IMAGE_RULE
    user = f"问题：{effective_query}\n\n参考资料：\n{context}"
    if image_detail:
        user += f"\n\n【图片识别内容】\n{image_detail}"
    splitter = ThinkAnswerSplitter()
    try:
        async for kind, payload in _model_stream(
            [{"role": "system", "content": system}] + chat_history + [user_message(user, image)],
            max_tokens,
            temperature,
            usage_box,
        ):
            if kind == "status":
                yield ("status", payload)
                continue
            for typ, text in splitter.feed(payload):
                if typ == "chunk":
                    answer_parts.append(text)
                elif typ == "reasoning":
                    reasoning_parts.append(text)
                yield (typ, text)
        for typ, text in splitter.flush():
            if typ == "chunk":
                answer_parts.append(text)
            elif typ == "reasoning":
                reasoning_parts.append(text)
            yield (typ, text)
    except ApiError as exc:
        # ★ 降级回答（用户要求："生成完全失败→至少返回检索到的资料片段，
        # 显示'已为您找到相关资料'"）。
        #
        # 检索已经成功了 —— 资料就在 sources 里。这时候最有价值的做法是把
        # 资料本身整理给用户，而不是报一句"模型服务异常"。用户问法规问题，
        # 他搜不到的那些条文原文本来就是他最需要的东西。
        #
        # sources_digest 不调模型，所以这段兜底不会再失败。
        # 真实原因进服务端日志。
        logger.warning("rag 生成失败，降级为资料直出（sources=%d）：%s",
                       len(sources), exc.tech_detail or exc.message)
        note = sources_digest(sources) if sources else retrieval_failed_note(sources)
        answer_parts.append(note)
        yield ("status", {"stage": "generate", "message": "已改为直接提供资料", "state": "done"})
        yield ("chunk", note)
        yield ("done", {
            "route": "rag",
            "sources": sources,
            "history_turns_used": len(chat_history),
            "latency_s": round(time.perf_counter() - started, 3),
            "model": MODEL_NAME,
            "degraded": True,
            "usage": usage_box.get("usage", {}),
        })
        return
    FAQ_CACHE.put(cache_key, {"content": "".join(answer_parts), "sources": sources,
                              "route": "rag",
                              "reasoning": "".join(reasoning_parts),
                              "usage": usage_box.get("usage", {})})
    yield ("status", {"stage": "generate", "message": "回答已生成", "state": "done"})
    yield ("done", {
        "route": "rag",
        "sources": sources,
        "history_turns_used": len(chat_history),
        "latency_s": round(time.perf_counter() - started, 3),
        "model": MODEL_NAME,

        "usage": usage_box.get("usage", {}),
    })



async def answer_query(request: Any) -> dict[str, Any]:
    """非流式：消费**同一个**事件流，拼出 JSON 响应。

    与流式端点共用 run_pipeline，因此两条通路的路由、检索、提示词、后处理
    永远一致——这正是 P2 之前最容易漂移的地方。

    入口校验也必须在这里做一份：流式端点（routes.py）在返回 StreamingResponse
    **之前**校验，而这条非流式通路原本**不校验** —— 于是 ``POST /hybrid_search {}``
    一路走到 run_pipeline 的兜底问题「请说明这张图片的内容」，**返回 200**。
    实测确认过：空对象 / query 空串 / query 全空格 / report=photo 不带图，
    四种都回 200 + route=general，用户拿到一个答非所问的答案却看不出是出错。
    """
    query = (request.query or request.question or "").strip()
    image = normalize_image(request.image)
    # 更具体的判断放前面：用户既然切到了照片模式，最该告诉他的是"要传图"，
    # 这比笼统的"请先输入问题或上传图片"更可操作。
    if (request.report or "") == "photo" and not image:
        raise ApiError("E_PHOTO_NEEDS_IMAGE",
                       "现场照片专业研判需要上传图片，请带上 image 字段")
    if not query and not image:
        raise ApiError("E_QUERY_EMPTY")

    route = ""
    sources: list[dict[str, Any]] = []
    reasoning_parts: list[str] = []
    answer_parts: list[str] = []
    image_note = ""
    done: dict[str, Any] = {}
    error: str | None = None
    error_code: str = "E_INTERNAL"

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
            # error 事件的载荷现在是 {"code","message"}（改动前是裸字符串）。
            # 两种都认，避免"事件形状变了但消费方没跟上"这种漂移。
            if isinstance(data, dict):
                error = data.get("message") or str(data)
                error_code = data.get("code") or "E_INTERNAL"
            else:
                error = str(data)
                error_code = "E_INTERNAL"

    answer = "".join(answer_parts)
    if error and not answer.strip():
        # 一个字的答案都没产出：按服务异常返回（与改动前的非流式行为一致）
        raise ApiError(error_code, error)

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
        # 有正文但也有错误：按 200 返回（与改动前一致），但把**错误码**一并带上，
        # 让前端至少能分辨"成功但有告警"和"成功且干净"。
        result["error"] = error
        result["error_code"] = error_code
    return result
