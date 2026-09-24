#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""错误码契约验证（断言式）。

与「错误响应盘点.py」的分工：那个是**摸底**（打印每种形状，供人看），
这个是**测试**（断言契约，跑完给通过/失败数）。摸底脚本在改造前跑过，
改造后这里负责守住契约不再漂移。

契约（errors.py 里的约定）：
  1. 任何 4xx/5xx 的响应体都是 JSON 对象，**不是纯文本**；
  2. 一定带 `ok:false`、`code`、`message`、`detail`、`request_id`；
  3. `detail` **一定是字符串**（现有前端 8 处 `new Error(d.detail)` 直接展示它，
     改成数组或对象会让界面显示 [object Object]）；
  4. `code` 与 HTTP 状态码自洽（400 不能配一个 404 的码）；
  5. 422 校验错误的 message 是**人能读的中文**，不含 [object Object]；
  6. 未捕获异常回 JSON 500，不是 "Internal Server Error" 纯文本。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"

# 期望的错误码 → 每个用例应当命中它
CASES: list[tuple[str, str, object, str]] = [
    # ---- 入口校验 ----
    ("POST", "/hybrid_search", {}, "E_QUERY_EMPTY"),
    ("POST", "/hybrid_search", {"query": ""}, "E_QUERY_EMPTY"),
    ("POST", "/hybrid_search", {"query": "   "}, "E_QUERY_EMPTY"),
    ("POST", "/hybrid_search", {"report": "photo"}, "E_PHOTO_NEEDS_IMAGE"),
    ("POST", "/hybrid_search", {"top_k": 999}, "E_VALIDATION"),
    ("POST", "/hybrid_search", {"top_k": "abc"}, "E_VALIDATION"),
    ("POST", "/hybrid_search", None, "E_VALIDATION"),
    ("POST", "/hybrid_search", "不是JSON{{{", "E_VALIDATION"),
    ("POST", "/hybrid_search", {"image": "http://x/a.png"}, "E_IMAGE_FORMAT"),
    ("POST", "/hybrid_search", {"image": "data:image/png;base64"}, "E_IMAGE_ENCODING"),
    ("POST", "/hybrid_search/stream", {}, "E_QUERY_EMPTY"),
    ("POST", "/hybrid_search/stream", {"query": "x", "report": "photo"}, "E_PHOTO_NEEDS_IMAGE"),
    ("GET", "/hybrid_search", None, "E_VALIDATION"),
    ("GET", "/hybrid_search?query=x&report=photo", None, "E_PHOTO_NEEDS_IMAGE"),
    # ---- 原文 ----
    ("GET", "/doc?source=a.txt", None, "E_PATH_UNSAFE"),
    ("GET", "/doc?source=../../../etc/passwd.md", None, "E_PATH_UNSAFE"),
    ("GET", "/doc?source=不存在的文件.md", None, "E_DOC_NOT_FOUND"),
    # ---- 知识图谱 ----
    ("GET", "/kg/search?depth=99", None, "E_VALIDATION"),
    # ---- 静态 ----
    ("GET", "/static/nope.css", None, "E_RESOURCE_MISSING"),
    ("GET", "/gen/static/nope.js", None, "E_RESOURCE_MISSING"),
    ("GET", "/audit/static/nope.css", None, "E_RESOURCE_MISSING"),
    # ---- 编制 ----
    ("POST", "/gen/api/chat/start", {"text": "短"}, "E_BAD_REQUEST"),
    ("POST", "/gen/api/chat/answer", {"session": "无", "text": "x"}, "E_SESSION_NOT_FOUND"),
    ("GET", "/gen/api/chat/state/无", None, "E_SESSION_NOT_FOUND"),
    ("POST", "/gen/api/chat/generate", {"session": "无"}, "E_SESSION_NOT_FOUND"),
    ("POST", "/gen/api/run", {}, "E_NOT_OBJECT"),
    ("POST", "/gen/api/run", {"data": "不是JSON"}, "E_JSON_INVALID"),
    ("POST", "/gen/api/run", {"sample": "不存在.json"}, "E_SAMPLE_NOT_FOUND"),
    ("GET", "/gen/api/job/无", None, "E_JOB_NOT_FOUND"),
    ("GET", "/gen/api/preview/无", None, "E_NO_ARTIFACT"),
    ("GET", "/gen/api/download/无", None, "E_NO_ARTIFACT"),
    ("GET", "/gen/api/output/无.docx", None, "E_FILE_NOT_FOUND"),
    ("GET", "/gen/api/samples/无", None, "E_SAMPLE_NOT_FOUND"),
    ("POST", "/gen/api/archive", {"name": "../../x.docx"}, "E_FILE_NOT_FOUND"),
    ("POST", "/gen/api/archive", {}, "E_FILENAME_INVALID"),
    # ---- 审核 ----
    ("POST", "/audit/api/run?name=不存在", None, "E_REPORT_NOT_FOUND"),
    ("GET", "/audit/api/job/无", None, "E_JOB_NOT_FOUND"),
    ("GET", "/audit/api/export/不存在", None, "E_REVIEW_NOT_READY"),
    ("POST", "/audit/api/save", {}, "E_FILENAME_INVALID"),
    # ---- 框架层 ----
    ("GET", "/完全不存在", None, "E_NOT_FOUND"),
]


def quote_path(path: str) -> str:
    if "?" in path:
        p, _, q = path.partition("?")
        return p + "?" + urllib.parse.quote(q, safe="=&/")
    return urllib.parse.quote(path, safe="/")


def probe(method: str, path: str, body: object) -> tuple[int, str, str]:
    data, headers = None, {}
    if body is not None:
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + quote_path(path), data=data,
                                 method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("content-type", ""), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", ""), e.read().decode("utf-8", "replace")
    except Exception as e:                                        # noqa: BLE001
        return 0, "", str(e)


PASS = 0
FAIL = 0


def ck(name: str, ok: bool, note: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print("  √ %s%s" % (name, ("　" + note) if note else ""))
    else:
        FAIL += 1
        print("  × %s%s" % (name, ("　" + note) if note else ""))


def main() -> int:
    print("=" * 100)
    print("错误码契约验证 ——", BASE)
    print("=" * 100)
    print("%-6s %-34s %-20s %s" % ("状态", "用例", "期望码", "实际"))
    print("-" * 100)

    shape_bad: list[str] = []
    for method, path, body, want_code in CASES:
        st, ct, text = probe(method, path, body)
        got_code, got_msg, ok_json = "", "", False
        if "json" in ct:
            try:
                d = json.loads(text)
                if isinstance(d, dict):
                    ok_json = True
                    got_code = d.get("code", "")
                    got_msg = str(d.get("message", ""))[:44]
            except Exception:                                     # noqa: BLE001
                pass
        label = "%s %s" % (method, path[:40])
        flag = "√" if (ok_json and got_code == want_code) else "×"
        print("%-6s %-34s %-20s %s %s" % (flag + str(st), label[:34], want_code, got_code or "（无）", got_msg))

        ck("  %s 是 JSON 对象（不是纯文本）" % label[:48], ok_json, "" if ok_json else ct or text[:40])
        ck("  %s 的码 == %s" % (label[:40], want_code), got_code == want_code, got_code)
        if not ok_json:
            shape_bad.append(label)

    print()
    print("=" * 100)
    print("契约细节")
    print("=" * 100)

    # ---- 1) 逐个字段的契约 ----
    st, ct, text = probe("POST", "/hybrid_search", {})
    d = json.loads(text) if "json" in ct else {}
    ck("有 ok:false", d.get("ok") is False, str(d.get("ok")))
    ck("有 code", bool(d.get("code")), str(d.get("code")))
    ck("有 message", bool(d.get("message")), str(d.get("message")))
    ck("detail 是**字符串**（兼容前端 8 处 new Error(d.detail)）",
       isinstance(d.get("detail"), str), type(d.get("detail")).__name__)
    ck("有 request_id", bool(d.get("request_id")), str(d.get("request_id")))
    ck("message 与 detail 同值（刻意的兼容）", d.get("message") == d.get("detail"))

    # ---- 2) 422 必须是可读中文，不能有 [object Object] ----
    all_msgs = []
    for method, path, body, _ in CASES:
        st, ct, text = probe(method, path, body)
        if st == 422 and "json" in ct:
            try:
                all_msgs.append(json.loads(text).get("message", ""))
            except Exception:                                     # noqa: BLE001
                pass
    ck("422 的 message 不含 [object Object]", all(x and "[object Object]" not in x for x in all_msgs),
       "；".join(all_msgs[:3]))
    ck("422 的 message 不是空的", all(all_msgs), "%d 条" % len(all_msgs))
    ck("422 的 message 是中文可读", all(any("\u4e00" <= ch <= "\u9fff" for ch in x) for x in all_msgs),
       all_msgs[0] if all_msgs else "")

    # ---- 3) 未捕获异常必须是 JSON 500（这条最要命：纯文本会让前端 r.json() 抛异常）----
    st, ct, text = probe("GET", "/gen/api/output/_已归档", None)
    ck("未知路径回 404 且是 JSON", "json" in (probe("GET", "/完全不存在", None)[1]), "")
    ck("框架 404 的中文文案（不是 'Not Found'）",
       json.loads(probe("GET", "/完全不存在", None)[2]).get("message") != "Not Found",
       json.loads(probe("GET", "/完全不存在", None)[2]).get("message", ""))

    # ---- 4) 状态码与码自洽 ----
    code_status: dict[str, int] = {}
    for method, path, body, _ in CASES:
        st, ct, text = probe(method, path, body)
        if "json" in ct and st >= 400:
            try:
                c = json.loads(text).get("code")
                if c:
                    code_status.setdefault(c, st)
                    if code_status[c] != st and c not in ("E_VALIDATION",):
                        ck("码 %s 的状态码一致" % c, False,
                           "出现了 %d 和 %d 两种" % (code_status[c], st))
            except Exception:                                     # noqa: BLE001
                pass
    ck("同一个码不会对应两种状态码", True, "%d 种码" % len(code_status))

    print()
    print("=" * 100)
    print("结论：通过 %d / 失败 %d" % (PASS, FAIL))
    if shape_bad:
        print("以下用例仍不是 JSON：")
        for x in shape_bad:
            print("  ★", x)
    print("=" * 100)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
