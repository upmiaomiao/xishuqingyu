"""第 3、4 项实测：缓存命中、重试文案、步骤收尾。

要证明的事：
  1. 同一个自包含问题问两次，第二次**命中缓存**（第 4 项 d）；
  2. ★ 反向：带图片 / 带多轮历史的提问**永远不命中缓存**
     —— 否则"发完图问什么都答图片"那个 bug 会借缓存复活；
  3. 每次 SSE 流结束时**没有还在转圈的步骤**（第 1 项的后端一半 + 之前那个 bug）；
  4. done 事件带 route / sources，前端才有东西可渲染。

判据落在真实 SSE 事件流上，不靠读代码猜。
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8011"
FAILS = []


def check(cond, desc):
    print(("  OK   " if cond else "  FAIL ") + desc)
    if not cond:
        FAILS.append(desc)


def section(t):
    print()
    print("=== %s ===" % t)


def stream(body, timeout=300):
    """打一次 SSE，返回解析后的事件列表 [(事件名, 载荷)]。"""
    req = urllib.request.Request(
        BASE + "/hybrid_search/stream",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    events = []
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            ev, data = "", ""
            for raw in r:
                line = raw.decode("utf-8", "replace").rstrip("\n")
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:"):
                    data += line[5:].strip()
                elif line == "":
                    if ev:
                        try:
                            events.append((ev, json.loads(data)))
                        except Exception:
                            events.append((ev, data))
                    ev, data = "", ""
    except urllib.error.HTTPError as e:
        events.append(("__http_error__", e.code))
    return events


def assess(events):
    """照抄前端 applyStatus 的折叠逻辑，判断结束时有没有步骤还在"运行中"。

    为什么要照抄而不是数事件：后端同一个 stage 会发多次 run（进度更新），
    直接数 run/done 会误判成"done 少了"（之前就误判过一次）。
    前端是把同 stage 的连续 run 合并成一步，只在 done 时才收尾。
    """
    open_steps = {}
    for ev, p in events:
        if ev != "status" or not isinstance(p, dict):
            continue
        stage = p.get("stage") or "?"
        if p.get("state") == "run":
            open_steps[stage] = p.get("message") or ""
        elif p.get("state") == "done":
            open_steps.pop(stage, None)
    # 前端还有一层兜底：流结束时把还在跑的收掉。
    # 这里**不**照抄那个兜底 —— 我们要看的就是"后端自己收干净了没有"。
    return open_steps


def done_of(events):
    for ev, p in reversed(events):
        if ev == "done" and isinstance(p, dict):
            return p
    return None


def answer_of(events):
    return "".join(p for ev, p in events if ev == "chunk" and isinstance(p, str))


# --------------------------------------------------------------------------
section("一、缓存：同一个自包含问题问两次")

Q = "危险废物贮存场所应当采取哪些防护措施？"

# 先清一下计数基线
try:
    with urllib.request.urlopen(BASE + "/cache/stats", timeout=10) as r:
        before = json.loads(r.read().decode())
    print("  基线：%s" % before)
except Exception as exc:
    before = {}
    print("  取基线失败：%s" % exc)

e1 = stream({"query": Q, "image": None, "history": []})
d1 = done_of(e1)
a1 = answer_of(e1)
print("  第 1 次：route=%s  cached=%s  正文 %d 字" %
      (d1 and d1.get("route"), d1 and d1.get("cached"), len(a1)))
check(d1 is not None, "第 1 次拿到 done 事件")
check(not (d1 or {}).get("cached"), "第 1 次是未命中（要真去生成）")
check(len(a1) > 20, "第 1 次有实际回答内容")
first_open = assess(e1)
check(not first_open, "第 1 次流结束时没有还在转圈的步骤（实际：%s）" % (first_open or "无"))

e2 = stream({"query": Q, "image": None, "history": []})
d2 = done_of(e2)
a2 = answer_of(e2)
print("  第 2 次：route=%s  cached=%s  正文 %d 字  耗时 %.2fs" %
      (d2 and d2.get("route"), d2 and d2.get("cached"), len(a2), (d2 or {}).get("latency_s") or -1))
check((d2 or {}).get("cached") is True, "★ 第 2 次**命中缓存**")
check(a2 == a1, "缓存返回的正文与第 1 次完全一致")
check((d2 or {}).get("model") == "cache", "done 里 model 标记为 cache")
check(assess(e2) == {}, "命中缓存时步骤也收干净了")

try:
    with urllib.request.urlopen(BASE + "/cache/stats", timeout=10) as r:
        after = json.loads(r.read().decode())
    print("  之后：%s" % after)
    check(after.get("hits", 0) >= 1, "/cache/stats 的 hits 计数涨了")
    check(after.get("size", 0) >= 1, "缓存里有条目了")
except Exception as exc:
    check(False, "读 /cache/stats 失败：%s" % exc)


# --------------------------------------------------------------------------
section("二、★ 反向：带图片 / 带历史的提问绝不能命中缓存")


def tiny_png():
    """1x1 透明 PNG 的 data URL。只用来说明"这次带了图"。"""
    import base64
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
        "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
    return "data:image/png;base64," + base64.b64encode(png).decode()


# 同一个问题，但这次带图 —— 绝不能用上面那条缓存
e3 = stream({"query": Q, "image": tiny_png(), "history": []})
d3 = done_of(e3)
print("  带图同问：route=%s cached=%s" % (d3 and d3.get("route"), d3 and d3.get("cached")))
check(not (d3 or {}).get("cached"),
      "★ 带图片的同一个问题**没有**命中缓存（上下文不同，答案不能串）")

# 同一个问题，但带多轮历史 —— 同样不能用缓存
e4 = stream({"query": Q, "image": None,
             "history": [{"role": "user", "content": "我先说一下背景：我们厂在江苏。"},
                         {"role": "assistant", "content": "好的，请继续。"}]})
d4 = done_of(e4)
print("  带历史同问：route=%s cached=%s" % (d4 and d4.get("route"), d4 and d4.get("cached")))
check(not (d4 or {}).get("cached"),
      "★ 带多轮历史的同一个问题**没有**命中缓存")
check(assess(e4) == {}, "带历史的这次步骤也收干净了")


# --------------------------------------------------------------------------
section("三、不同的问题不该互相命中")

e5 = stream({"query": "排污许可证有效期是几年？", "image": None, "history": []})
d5 = done_of(e5)
check(not (d5 or {}).get("cached"), "换个问题 → 未命中（缓存没有乱串）")
check(len(answer_of(e5)) > 10, "换个问题也有实际回答")


# --------------------------------------------------------------------------
section("四、普通问答的步骤收尾（之前那个'转圈不停'的 bug）")

for label, body in (
    ("纯文字法规问题", {"query": "危险废物转移联单要保存几年？", "image": None, "history": []}),
    ("打招呼（direct_chat 通路）", {"query": "你好", "image": None, "history": []}),
    ("科普类（general 通路）", {"query": "什么是环境影响评价？", "image": None, "history": []}),
):
    ev = stream(body)
    op = assess(ev)
    dn = done_of(ev)
    check(not op, "%-22s 结束时无转圈步骤（route=%s）" % (label, dn and dn.get("route")))
    check(dn is not None and dn.get("route"), "%-22s done 事件带 route" % label)
    check("sources" in (dn or {}), "%-22s done 事件带 sources 字段" % label)


# --------------------------------------------------------------------------
section("五、降级标记字段存在（第 4 项 b/c 的接口约定）")

# 正常生成时不该出现 degraded=True
check(not (d1 or {}).get("degraded"), "正常回答不带 degraded 标记（反向断言）")
# done 里应当有这个字段的约定位（前端读的是布尔真值，缺省 falsy 即可）
print("  done 事件字段：%s" % sorted((d1 or {}).keys()))


print()
if FAILS:
    print("失败 %d 项：" % len(FAILS))
    for f in FAILS:
        print("  · " + f)
    sys.exit(1)
print("全部通过。")
