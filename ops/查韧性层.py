"""韧性层单测：重试、降级、缓存（用户提的第 4 项）。

在服务器上用 .venv 的 python 跑 —— 那里才有 fastapi（resilience.py 通过
errors.py 间接依赖它），本地裸 python 没有。

每条断言都配了**反向断言**：只验"好的情况通过"是不够的，
必须同时验"坏的情况会被拦下"，否则测试可能只是在空转。
"""
import asyncio
import sys
import time

sys.path.insert(0, "/home/test/xishu_qingyu_serve")

from xishu_pipeline.errors import ApiError                     # noqa: E402
from xishu_pipeline.resilience import (DEGRADED_CHAT_NOTE, FaqCache,   # noqa: E402
                                       PHOTO_DEGRADED_NOTE,
                                       retrieval_failed_note,
                                       sources_digest, stream_with_retry)

FAILS = []


def check(cond, desc):
    if cond:
        print("  OK   " + desc)
    else:
        print("  FAIL " + desc)
        FAILS.append(desc)


def section(t):
    print()
    print("=== %s ===" % t)


# --------------------------------------------------------------------------
# 一、重试
# --------------------------------------------------------------------------
section("一、带重试的模型流")

calls = {"n": 0}


async def flaky_then_ok(*a, **kw):
    """前两次抛连接错误，第三次正常产出。"""
    calls["n"] += 1
    if calls["n"] <= 2:
        raise ConnectionError("模拟连接被拒 #%d" % calls["n"])
    for piece in ("你", "好", "。"):
        yield piece


async def run_flaky():
    kinds, text = [], []
    async for kind, payload in stream_with_retry(flaky_then_ok, retries=2):
        kinds.append(kind)
        if kind == "content":
            text.append(payload)
    return kinds, text


kinds, text = asyncio.run(run_flaky())
check(calls["n"] == 3, "失败两次后第三次成功（实际调用 %d 次）" % calls["n"])
check(kinds == ["retry", "retry", "content", "content", "content"],
      "重试事件按预期产出：%s" % kinds)
check("".join(text) == "你好。", "正文完整且**没有重复**（正是重试最容易搞砸的地方）")


async def always_fail(*a, **kw):
    raise ConnectionError("模拟一直连不上")
    yield  # pragma: no cover


async def run_always_fail():
    async for _ in stream_with_retry(always_fail, retries=2):
        pass


try:
    asyncio.run(run_always_fail())
    check(False, "重试耗尽后应当抛 ApiError")
except ApiError as exc:
    check(exc.code == "E_MODEL_UNAVAILABLE", "重试耗尽抛出 E_MODEL_UNAVAILABLE")
    check(exc.message == "模型服务暂时不可用，请稍后重试", "给用户的话是友好的：%s" % exc.message)
    check("重试 2 次仍失败" in (exc.tech_detail or ""), "真实原因留在 tech_detail 里供排查")

# —— 反向断言：**已经产出过内容就不许重试** ——
# 这是整个重试逻辑里最容易写错、后果最难看的一处：正文会被讲两遍。
partial = {"n": 0}


async def die_midway(*a, **kw):
    partial["n"] += 1
    yield "开头这段"
    raise ConnectionError("吐了一半断了")


async def run_midway():
    got = []
    async for kind, payload in stream_with_retry(die_midway, retries=2):
        if kind == "content":
            got.append(payload)
    return got


try:
    asyncio.run(run_midway())
    check(False, "中途失败也应当抛出（而不是静默结束）")
except ApiError as exc:
    check("已产出内容，不重试" in (exc.tech_detail or ""),
          "中途失败时**拒绝重试**，避免正文重复")
check(partial["n"] == 1, "中途失败只调用了 1 次（没有重试）")


# --------------------------------------------------------------------------
# 二、降级
# --------------------------------------------------------------------------
section("二、降级回答")

FAKE_SOURCES = [
    {"index": 1, "title": "报废机动车拆解企业污染控制技术规范",
     "source": "生态环境标准规范/标准解读/拆解/答记者问.md",
     "text": "拆解企业应当……" * 40},
    {"index": 2, "title": "固体废物污染环境防治法",
     "source": "生态环境法律法规/固废法.md",
     "text": "产生工业固体废物的单位应当……"},
]

digest = sources_digest(FAKE_SOURCES)
check("已为您找到相关资料" in digest, "降级文案包含用户要求的「已为您找到相关资料」")
check("[1]" in digest and "[2]" in digest, "两条资料都列出来了")
check("报废机动车拆解企业污染控制技术规范" in digest, "带上了资料标题")
check("生态环境法律法规/固废法.md" in digest, "带上了来源路径（用户可据此点开原文）")
# 长片段必须截断，否则降级回答会变成几千字的原文倾倒
check(len(digest) < 1400, "长片段被截断（总长 %d 字）" % len(digest))

check(sources_digest([]) == "", "没有资料时 sources_digest 返回空串（交给下一个兜底）")

note = retrieval_failed_note([])
check("没有检索到" in note, "检索也没结果时给的是「没找到」而不是「出错了」")


# —— 反向断言：降级文案里**不能**出现任何技术痕迹 ——
# 用户明确要求"界面不显示错误"。如果这些文案里混进了异常类名，
# 那就等于把错误换个地方显示了。
TECH_WORDS = ["Error", "Exception", "Traceback", "httpx", "ConnectError",
              "Timeout", "None", "HTTP", "502", "500"]
for label, text in (("DEGRADED_CHAT_NOTE", DEGRADED_CHAT_NOTE),
                    ("PHOTO_DEGRADED_NOTE", PHOTO_DEGRADED_NOTE),
                    ("retrieval_failed_note", note),
                    ("sources_digest", digest)):
    hit = [w for w in TECH_WORDS if w in text]
    check(not hit, "%s 不含技术痕迹（命中的：%s）" % (label, hit or "无"))


# --------------------------------------------------------------------------
# 三、缓存
# --------------------------------------------------------------------------
section("三、高频问题缓存")

c = FaqCache(ttl=60, maxsize=3)
k = c.key_for("危险废物贮存的场所要求是什么？", has_image=False, history=None)
check(k is not None, "自包含的问题可以缓存")
check(k == c.key_for("危险废物贮存的场所要求是什么", has_image=False, history=None),
      "标点/问号差异归一化成同一个键")
check(k == c.key_for("  危险废物贮存的场所要求是什么？  ", has_image=False, history=None),
      "首尾空格也被归一化")

# —— 反向断言：带图片或带历史的问题**必须**不缓存 ——
# 这是之前"发完图之后问什么都答图片"那个 bug 的翻版：
# 同一个「111」在不同上下文里意思完全不同，缓存会让答案串味。
check(c.key_for("111 这是啥", has_image=True, history=None) is None,
      "带图片的提问不缓存（防止上下文串味）")
check(c.key_for("那它有什么要求", has_image=False,
                history=[{"role": "user", "content": "x"}]) is None,
      "带多轮历史的提问不缓存")
check(c.key_for("111", has_image=False, history=None) is None,
      "过短的问题不缓存（没有信息量，容易互相撞键）")

c.put(k, {"content": "答案正文", "sources": [], "route": "rag"})
got = c.get(k)
check(got is not None and got["content"] == "答案正文", "写入后能读出")
check(c.hits == 1, "命中计数正确")
c.get("不存在的键")
check(c.misses == 1, "未命中计数正确")

# 过期
c2 = FaqCache(ttl=0.05, maxsize=3)
k2 = c2.key_for("过期测试问题内容", has_image=False, history=None)
c2.put(k2, {"content": "旧答案"})
time.sleep(0.12)
check(c2.get(k2) is None, "超过 TTL 后不再返回旧答案")

# LRU 淘汰
c3 = FaqCache(ttl=600, maxsize=2)
for i in range(3):
    c3.put("键%d内容够长" % i, {"content": "答案%d" % i})
check(c3.stats()["size"] == 2, "超过上限后按 LRU 淘汰（当前 %d 条）" % c3.stats()["size"])
check(c3.get("键0内容够长") is None, "最久未使用的先被淘汰")
check(c3.get("键2内容够长") is not None, "最近使用的还在")

st = c3.stats()
check("hit_rate" in st and "size" in st, "stats() 给出可观测字段：%s" % sorted(st))


# --------------------------------------------------------------------------
print()
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for f in FAILS:
        print("  · " + f)
    sys.exit(1)
print("全部通过。")
