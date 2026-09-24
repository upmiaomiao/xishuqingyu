"""韧性层：重试、降级、缓存 —— 让"模型抽风"不再等于"用户看到报错"。

为什么单独一个模块
==================
用户的原话：「自动重试 1-2 次，很多瞬时故障重试就好；主模型失败→降级到
'检索+摘要'模式，至少给基于资料的回答；生成完全失败→至少返回检索到的资料片段；
高频常见问题答案本地缓存，命中直接返回。」

这四件事都属于"出问题时的兜底"，跟检索、提示词、渲染没有关系，
混在 pipeline.py 里会让那个本来就长的文件更难读。所以单独放这里。

三条设计原则
------------
1. **只在"还来得及"的时候重试。** 一旦已经往流里吐过正文，重试会导致
   正文重复（用户会看到两段开头）。所以 `stream_with_retry` 只在**一个字符
   都没产出**时才重试；已经开始输出就立刻放弃重试、直接把错误往上抛。

2. **降级也要是"有用的话"，不能是"抱歉我失败了"。** 检索已经成功时，
   资料就在手里 —— 这时候最该做的是把资料整理给用户，而不是报错。
   `sources_digest` 就是干这个的：不调模型，直接按命中顺序列出要点。

3. **缓存只服务"自包含"的问题。** 带图片、带多轮历史的提问高度依赖上下文，
   缓存它们的答案会串味（就像之前那个"发完图之后问什么都答图片"的 bug）。
   所以 `FaqCache.key_for` 遇到 image 或 history 直接返回 None —— 不缓存。
"""
from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from typing import Any, AsyncIterator, Callable

from .errors import ApiError

# --------------------------------------------------------------------------
# 一、重试
# --------------------------------------------------------------------------

# 重试次数。默认 2 次（共尝试 3 次）—— 与用户说的"1-2 次"一致。
# 为什么不更多：模型服务真的挂了的话，多试只是让用户多等；
# 而 vLLM 这类服务偶发的连接抖动，试 1~2 次基本都能过。
DEFAULT_RETRIES = 2
RETRY_BASE_DELAY = 0.6      # 秒，第 n 次重试前等 RETRY_BASE_DELAY * n


async def stream_with_retry(
    call: Callable[..., AsyncIterator[str]],
    /,
    *args: Any,
    retries: int = DEFAULT_RETRIES,
    **kwargs: Any,
) -> AsyncIterator[tuple[str, Any]]:
    """带重试的模型流。产出 ``("retry", 第几次)`` 或 ``("content", 文本)``。

    为什么产出元组而不是只产出文本：调用方（pipeline 的生成器）需要
    **往 SSE 流里插一条"正在重新处理"的 status**，而它在 `async for` 里
    是被阻塞的，没法从回调里 yield。让本函数把"发生了重试"当成一种
    正常产出物报上去，调用方就能自然地 yield 出去。

    只用 `call` + `args`/`kwargs` 而不是写死 stream_model：
    这样测试里能塞一个会失败两次的假函数进来，不用真去打模型。
    """
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        produced = False
        try:
            async for chunk in call(*args, **kwargs):
                produced = True
                yield ("content", chunk)
            return
        except Exception as exc:                                   # noqa: BLE001
            last_exc = exc
            if produced:
                # ★ 已经吐过正文了：重试会造成正文重复，只能放弃。
                # 这一点必须显式判断 —— 否则用户会看到回答被讲两遍。
                raise ApiError(
                    'E_MODEL_UNAVAILABLE',
                    "回答生成中断，请重试",
                    detail=f"流式输出中途失败，已产出内容，不重试：{exc!r}",
                )
            if attempt >= retries:
                break
            yield ("retry", attempt + 1)
            await asyncio.sleep(RETRY_BASE_DELAY * (attempt + 1))
    raise ApiError(
        'E_MODEL_UNAVAILABLE',
        "模型服务暂时不可用，请稍后重试",
        detail=f"重试 {retries} 次仍失败：{last_exc!r}",
    )


# --------------------------------------------------------------------------
# 二、降级：把检索到的资料直接整理成回答（不调模型）
# --------------------------------------------------------------------------

def sources_digest(sources: list[dict[str, Any]], limit: int = 4) -> str:
    """检索成功但生成失败时，把资料本身整理成一段可读的回答。

    这不是"敷衍的兜底"—— 用户来问法规问题，最有价值的东西本来就是他
    搜不到的那些条文原文。模型写不出综述时，把命中资料按相关度列出来
    仍然解决了他的大部分问题。

    不调模型，所以这段永远不会再失败。
    """
    if not sources:
        return ""
    lines = ["已为您找到相关资料。以下是检索到的内容要点：", ""]
    for s in sources[:limit]:
        title = str(s.get("title") or "").strip() or "（无标题）"
        src = str(s.get("source") or "").strip()
        text = re.sub(r"\s+", " ", str(s.get("text") or "")).strip()
        if len(text) > 260:
            text = text[:260] + "…"
        lines.append(f"**[{s.get('index', '?')}] {title}**")
        if src:
            lines.append(f"来源：{src}")
        if text:
            lines.append(text)
        lines.append("")
    lines.append("以上资料由检索系统按相关度排序给出。若需要更完整的分析，请稍后重试。")
    return "\n".join(lines)


def retrieval_failed_note(sources: list[dict[str, Any]]) -> str:
    """连检索都没有结果时的说明。不是错误，只是没找到。"""
    return (
        "没有检索到与您的问题直接相关的资料。\n\n"
        "可能的原因：问题涉及的领域暂未收录，或表述可以更具体一些。"
        "您可以换一种说法再问一次，比如补上地区、行业或具体环节。"
    )


# 没有资料可降级的通路（直接对话 / 科普问答）彻底失败时给的话。
# 刻意不写任何技术细节：真实原因进服务端日志和浏览器控制台，
# 界面上只让用户知道"出了点问题、重试通常能好"。
DEGRADED_CHAT_NOTE = (
    "抱歉，刚才生成回答时服务出现了短暂问题，这次没能给出结果。\n\n"
    "您可以直接把问题再发一次 —— 大多数情况下重试就能成功。"
)

# 照片研判彻底失败时的话。研判要出结构化 JSON 才能渲染成报告，
# 没有 JSON 就渲染不出核验清单 —— 与其给一份缺项的假报告，不如说清楚。
PHOTO_DEGRADED_NOTE = (
    "抱歉，现场照片研判这次没能生成完成。\n\n"
    "照片已经识别成功，但研判报告的结构化内容生成失败。"
    "您可以再发一次这张照片；如果反复失败，换一张更清晰的图片通常会有帮助。"
)


# --------------------------------------------------------------------------
# 三、高频问题缓存
# --------------------------------------------------------------------------

CACHE_TTL = 30 * 60        # 30 分钟。索引更新后最迟半小时内失效
CACHE_MAX = 300            # 最多 300 条，超出按 LRU 淘汰

# 归一化时要剥掉的标点：空白 + 中英文标点。
#
# 用**单引号**的 raw 字符串写：里面那个 ASCII 双引号就不需要转义了。
# 单引号本身写成 \x27 —— 在 raw 单引号字符串里直接写 ' 会把字符串截断。
#
# 上一版写成 r"[...""''...]" 是个真 bug，不是风格问题：字符串在第 32 个字符
# 处被 ASCII 双引号截断，后半段变成了**非** raw 字符串，于是
#   ① \[ 触发了 SyntaxWarning；
#   ② 更要命的是 \\ 的语义从"两个字符（正则转义的反斜杠）"变成"一个字符"，
#      字符类实际匹配的东西和写的人以为的不一样。
# 教训：字符类里有引号时，先选一个不会撞的引号，再写。
_PUNCT = re.compile(r'[\s，。？！、；："\x27（）【】《》,.?!;:()\[\]{}<>`~@#$%^&*+=|\\/—-]+')



def normalize_question(q: str) -> str:
    """把问题归一化成缓存键：去掉空白与标点、统一小写。

    「危废贮存有什么要求？」和「危废贮存有什么要求」应当命中同一条 ——
    用户多打一个问号不该导致缓存未命中。
    """
    return _PUNCT.sub("", (q or "").strip().lower())


class FaqCache:
    """带 TTL 的 LRU 缓存。

    为什么不用 functools.lru_cache：它没有过期时间，索引更新后会把旧答案
    一直发下去；而且它按参数元组缓存，这里要按"归一化后的问题+路由"缓存。
    """

    def __init__(self, ttl: float = CACHE_TTL, maxsize: int = CACHE_MAX) -> None:
        self.ttl = ttl
        self.maxsize = maxsize
        self._d: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    def key_for(self, query: str, *, has_image: bool, history: list | None) -> str | None:
        """算缓存键。返回 None 表示**这条不该缓存**。

        ★ 带图片或带多轮历史的提问一律不缓存。
        它们高度依赖上下文：同一个「111」在不同对话里意思完全不同，
        缓存会让答案串味 —— 之前那个"发完图之后问什么都答图片"的 bug
        就是这么来的，不能再用缓存把它请回来。
        """
        if has_image or history:
            return None
        k = normalize_question(query)
        # 太短的不缓存（"111"、"你好" 这类没有信息量，缓存下来只会互相撞键）
        return k if len(k) >= 4 else None

    def get(self, key: str | None) -> dict[str, Any] | None:
        if not key:
            return None
        item = self._d.get(key)
        if item is None:
            self.misses += 1
            return None
        ts, value = item
        if time.time() - ts > self.ttl:
            self._d.pop(key, None)
            self.misses += 1
            return None
        self._d.move_to_end(key)
        self.hits += 1
        return value

    def put(self, key: str | None, value: dict[str, Any]) -> None:
        if not key:
            return
        self._d[key] = (time.time(), value)
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "size": len(self._d),
            "maxsize": self.maxsize,
            "ttl_s": self.ttl,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
        }

    def clear(self) -> None:
        self._d.clear()


# 全站共用一个缓存实例
FAQ_CACHE = FaqCache()
