#!/usr/bin/env python3
# 针对性验证 P0-1 是否已修复：专业/法规类问题此前 100% HTTP 502
# 「检索服务异常：HTTPConnectionPool(host='127.0.0.1', port=34004) ... Connection refused」。
import json
import sys
import urllib.error
import urllib.request

SITE = "http://10.201.31.10:8011"

QUESTIONS = [
    "环境影响评价的适用范围是什么？",
    "固体废物污染环境防治法对危险废物贮存有什么要求？",
    "建设项目环境影响报告书应当包括哪些内容？",
    "大气污染物综合排放标准中颗粒物的排放限值是多少？",
]


def post(path, payload, timeout=240):
    req = urllib.request.Request(
        SITE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw[:400]


ok = 0
for q in QUESTIONS:
    st, body = post("/hybrid_search", {"query": q})
    if not isinstance(body, dict):
        print(f"[{st}] 非 JSON 响应：{body}")
        continue
    ans = body.get("answer") or ""
    srcs = body.get("sources") or []
    broken = "检索服务异常" in ans
    verdict = "OK" if (st == 200 and not broken) else "FAIL"
    if verdict == "OK":
        ok += 1
    print(f"[{verdict}] HTTP {st}  route={body.get('route')!r}  来源数={len(srcs)}  "
          f"检索异常={'是' if broken else '否'}  问题={q}")
    if srcs:
        first = srcs[0]
        name = first.get("file") or first.get("title") or first.get("source") or list(first)[:3]
        print(f"        首个来源：{name}")
    if broken:
        print(f"        答复片段：{ans[:200]}")

print(f"\n结果：{ok}/{len(QUESTIONS)} 通过")
sys.exit(0 if ok == len(QUESTIONS) else 1)
