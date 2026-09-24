#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误响应实测盘点：把每个接口的坏输入都打一遍，把**真实的**错误响应录下来。

为什么要实测而不是读代码：FastAPI 的错误形状取决于有没有自定义异常处理器，
读代码只能猜。实测能直接看到三种形状混在一起：
  · HTTPException            → {"detail": "<字符串>"}
  · RequestValidationError   → {"detail": [{"loc":..,"msg":..,"type":..}]}   ← 数组！
  · 未捕获异常                → 纯文本 "Internal Server Error"               ← 不是 JSON！
第三种最要命：前端 `r.json()` 会直接抛异常，于是"报错"变成"界面什么都不发生"。

输出：每个用例一行，标出 status / content-type / 形状 / 有没有错误码。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def _quote_path(path: str) -> str:
    """把路径里的非 ASCII（中文报告名等）百分号编码。
    第一版没做这件事，于是 12 个带中文参数的用例全部"连接失败" —— 那是**脚本的 bug**，
    不是服务端的问题（HTTP 请求行里不允许出现原始非 ASCII 字节）。"""
    if "?" in path:
        p, _, q = path.partition("?")
        return p + "?" + urllib.parse.quote(q, safe="=&/")
    return urllib.parse.quote(path, safe="/")

# (方法, 路径, 请求体或 None, 说明)
CASES: list[tuple[str, str, object, str]] = [
    # ---------- 法规问答 ----------
    ("POST", "/hybrid_search", {}, "空对象（P2-1 已知问题）"),
    ("POST", "/hybrid_search", {"query": ""}, "query 空串"),
    ("POST", "/hybrid_search", {"query": "   "}, "query 全空格"),
    ("POST", "/hybrid_search", {"top_k": 999}, "top_k 越界"),
    ("POST", "/hybrid_search", {"top_k": "abc"}, "top_k 类型错"),
    ("POST", "/hybrid_search", {"temperature": -5}, "temperature 越界"),
    ("POST", "/hybrid_search", {"history": "不是数组"}, "history 类型错"),
    ("POST", "/hybrid_search", None, "没有请求体"),
    ("POST", "/hybrid_search", "不是JSON{{{", "请求体不是 JSON"),
    ("POST", "/hybrid_search", {"report": "photo"}, "photo 模式但没带图"),
    ("POST", "/hybrid_search", {"image": "http://x/a.png"}, "图片不是 data URL"),
    ("POST", "/hybrid_search", {"image": "data:image/png;base64"}, "图片缺 ;base64,"),
    ("POST", "/hybrid_search/stream", {}, "流式：空对象"),
    ("POST", "/hybrid_search/stream", {"query": ""}, "流式：query 空串"),
    ("POST", "/hybrid_search/stream", None, "流式：没有请求体"),
    ("POST", "/hybrid_search/stream", "{{{", "流式：不是 JSON"),
    ("GET", "/hybrid_search", None, "GET 缺 query（必填）"),
    ("GET", "/hybrid_search?query=x&top_k=99", None, "GET top_k 越界"),
    ("GET", "/hybrid_search?query=x&report=photo", None, "GET 请求 photo 模式"),
    # ---------- 原文 ----------
    ("GET", "/doc", None, "缺 source"),
    ("GET", "/doc?source=a.txt", None, "source 不是 .md"),
    ("GET", "/doc?source=../../../etc/passwd.md", None, "目录穿越尝试"),
    ("GET", "/doc?source=不存在的文件.md", None, "文件不存在"),
    # ---------- 知识图谱 ----------
    ("GET", "/kg/search?depth=99", None, "depth 越界"),
    ("GET", "/kg/search?limit=1", None, "limit 低于下限"),
    # ---------- 静态 ----------
    ("GET", "/static/nope.css", None, "白名单外的资源"),
    ("GET", "/static/../../routes.py", None, "静态目录穿越"),
    ("GET", "/gen/static/nope.js", None, "gen 白名单外"),
    ("GET", "/audit/static/nope.css", None, "audit 白名单外"),
    # ---------- 报告编制 ----------
    ("POST", "/gen/api/chat/start", {}, "缺 text"),
    ("POST", "/gen/api/chat/start", {"text": "短"}, "text 太短"),
    ("POST", "/gen/api/chat/answer", {"session": "不存在", "text": "x"}, "session 不存在"),
    ("POST", "/gen/api/chat/skip", {"session": "不存在"}, "skip session 不存在"),
    ("GET", "/gen/api/chat/state/不存在", None, "state 不存在"),
    ("POST", "/gen/api/chat/generate", {"session": "不存在"}, "generate session 不存在"),
    ("POST", "/gen/api/chat/reset", {}, "reset 缺 session"),
    ("POST", "/gen/api/run", {}, "run 空对象"),
    ("POST", "/gen/api/run", {"data": "不是JSON"}, "run data 不是 JSON"),
    ("POST", "/gen/api/run", {"data": [1, 2]}, "run data 不是对象"),
    ("POST", "/gen/api/run", {"sample": "不存在.json"}, "run 样例不存在"),
    ("GET", "/gen/api/job/不存在", None, "job 不存在"),
    ("GET", "/gen/api/preview/不存在", None, "preview 不存在"),
    ("GET", "/gen/api/download/不存在", None, "download 不存在"),
    ("GET", "/gen/api/output/不存在.docx", None, "output 不存在"),
    ("GET", "/gen/api/samples/不存在", None, "样例不存在"),
    ("POST", "/gen/api/archive", {"name": "../../x.docx"}, "归档路径穿越"),
    ("POST", "/gen/api/delete", {"name": "../../x.docx"}, "删除路径穿越"),
    ("POST", "/gen/api/archive", {}, "归档缺 name"),
    # ---------- 报告审核 ----------
    ("GET", "/audit/api/review/不存在", None, "review 不存在"),
    ("POST", "/audit/api/run?name=不存在", None, "run 报告不存在"),
    ("GET", "/audit/api/job/不存在", None, "审核 job 不存在"),
    ("GET", "/audit/api/export/不存在", None, "export 不存在"),
    ("POST", "/audit/api/save", {}, "save 空对象"),
    ("GET", "/audit/api/export/../../etc/passwd?fmt=csv", None, "审核导出穿越"),
    # ---------- 文档面 ----------
    ("GET", "/docs", None, "Swagger UI 是否敞开"),
    ("GET", "/openapi.json", None, "OpenAPI 是否敞开"),
    ("GET", "/完全不存在", None, "未知路径"),
    # ---------- 专找未捕获的 500 ----------
    # 未捕获异常的响应形状最要命：Starlette 的 ServerErrorMiddleware 回的是
    # **纯文本** "Internal Server Error"，前端 r.json() 直接抛异常 →
    # "报错"变成"界面什么都不发生"。所以专门试几个容易踩到的路径。
    ("GET", "/gen/api/output/_已归档", None, "output 指向一个目录"),
    ("GET", "/gen/api/output/..%2f..%2froutes.py", None, "output 编码穿越"),
    ("GET", "/doc?source=.md", None, "source 只有后缀，stem 为空"),
    ("GET", "/doc?source=/", None, "source 是斜杠"),
    ("GET", "/audit/api/export/不存在?fmt=../../x", None, "导出 fmt 穿越"),
    ("POST", "/gen/api/delete", {"name": "_已归档"}, "删除一个目录"),
    ("GET", "/gen/api/preview_file/..%2f..%2froutes.py", None, "preview_file 穿越"),
    ("POST", "/hybrid_search", {"query": "x", "max_tokens": 128}, "合法的最小请求（对照）"),
]


def probe(method: str, path: str, body: object) -> tuple[int, str, str, str]:
    data = None
    headers = {}
    if body is not None:
        if isinstance(body, str):
            data = body.encode()
            headers["Content-Type"] = "application/json"
        else:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + _quote_path(path), data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("content-type", ""), r.read().decode("utf-8", "replace"), ""
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace"), ""
    except Exception as e:                                        # noqa: BLE001
        return 0, "", "", str(e)


def classify(status: int, ctype: str, text: str) -> tuple[str, str]:
    """返回 (形状, 摘要)。形状就是前端要分别处理的东西。"""
    if status == 0:
        return "连接失败", text[:60]
    if "event-stream" in ctype:
        return "SSE", "（流式，错误在事件里）"
    if "json" not in ctype:
        return "**纯文本（非 JSON）**", text.strip()[:60]
    try:
        d = json.loads(text)
    except Exception:                                             # noqa: BLE001
        return "**JSON 解析失败**", text[:60]
    if not isinstance(d, dict):
        return "JSON 非对象", str(type(d).__name__)
    if "detail" not in d:
        return "JSON 无 detail 字段", json.dumps(d, ensure_ascii=False)[:60]
    det = d["detail"]
    if isinstance(det, str):
        return "detail 字符串", det[:60]
    if isinstance(det, list):
        first = det[0] if det else {}
        if isinstance(first, dict):
            loc = ".".join(str(x) for x in (first.get("loc") or []))
            return "**detail 数组（422 校验）**", f"{loc}: {first.get('msg', '')}"[:60]
        return "detail 数组", str(det)[:60]
    return "detail 其他类型", str(det)[:60]


def main() -> int:
    print("=" * 118)
    print("错误响应实测盘点 —— ", BASE)
    print("=" * 118)
    print("%-6s %-30s %-6s %-22s %s" % ("状态", "用例", "码", "响应形状", "内容摘要"))
    print("-" * 118)

    shapes: dict[str, int] = {}
    no_code = 0
    problems: list[str] = []

    for method, path, body, desc in CASES:
        st, ct, text, err = probe(method, path, body)
        shape, summary = classify(st, ct, text)
        shapes[shape] = shapes.get(shape, 0) + 1
        # "有没有错误码"：JSON 里除了 detail 还有没有 code 字段
        has_code = False
        if "json" in ct:
            try:
                d = json.loads(text)
                has_code = isinstance(d, dict) and bool(d.get("code"))
            except Exception:                                     # noqa: BLE001
                pass
        if not has_code and st >= 400:
            no_code += 1
        mark = ""
        if st == 200 and method in ("POST", "GET") and "hybrid_search" in path and desc.startswith("空对象"):
            mark = "  ← 应为 400"
            problems.append(f"{method} {path} {desc}：返回 {st}，应为 400")
        if "纯文本" in shape or "解析失败" in shape:
            mark = "  ← 前端 r.json() 会抛异常"
            problems.append(f"{method} {path} {desc}：{shape}")
        if st == 0:
            problems.append(f"{method} {path} {desc}：连不上 {summary}")
        print("%-6s %-30s %-6s %-22s %s%s" % (
            method + " " + str(st), desc[:30], st, shape, summary, mark))

    print("-" * 118)
    print()
    print("响应形状分布：")
    for k, v in sorted(shapes.items(), key=lambda x: -x[1]):
        print("  %-26s %d" % (k, v))
    print()
    print("返回 4xx/5xx 但没有错误码（code 字段）的用例：%d / %d" % (no_code, len(CASES)))
    print()
    print("=" * 118)
    print("需要注意的：")
    for p in problems:
        print("  ★ " + p)
    if not problems:
        print("  （无）")
    print("=" * 118)
    return 0


if __name__ == "__main__":
    sys.exit(main())
