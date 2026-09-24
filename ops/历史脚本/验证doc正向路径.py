#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证 /doc 正向路径：从 API 返回的真实 source 里找一个能 200 的，并校验是真 PDF。

教训：上一版我在 shell 里手打 source 字符串，漏掉了路径前缀 → 得到假的 404。
本版一律用 API 原样返回的 source，不手工拼。
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def get(path, timeout=180):
    r = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), dict(resp.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode(), {}


def hget(headers, name):
    """大小写不敏感取响应头。

    坑：uvicorn 发的是小写键（content-type），dict.get("Content-Type") 会得到 None，
    从而把"正常返回"误判成"缺头"。本项目已踩过这个坑，这里统一用这个函数。
    """
    low = {k.lower(): v for k, v in headers.items()}
    return low.get(name.lower())


def main():
    st, b, _ = get("/hybrid_search?query=" + urllib.parse.quote("危险废物贮存污染控制标准有哪些要求"))
    d = json.loads(b.decode("utf-8"))
    srcs = [s for s in (d.get("sources") or []) if str(s.get("source", "")).lower().endswith(".md")]
    print("该问题共 %d 条 .md 引用\n" % len(srcs))

    ok = fail = 0
    first_ok = None
    for s in srcs:
        src = s["source"]                      # ← 原样用，不手工拼
        dst, db, dh = get("/doc?source=" + urllib.parse.quote(src), timeout=180)
        if dst == 200:
            ok += 1
            if first_ok is None:
                first_ok = (src, db, dh)
            print("  √ 200  %-56s %s %d 字节" % (src[-56:], hget(dh, "Content-Type"), len(db)))
        else:
            fail += 1
            try:
                detail = json.loads(db.decode("utf-8")).get("detail", "")[:60]
            except Exception:                                  # noqa: BLE001
                detail = db[:60]
            print("  × %-3s  %-56s %s" % (dst, src[-56:], detail))

    print("\n结果：200 共 %d 条，非 200 共 %d 条" % (ok, fail))

    if first_ok:
        src, db, dh = first_ok
        print("\n=== 可点开的引用卡片：响应头与内容校验 ===")
        print("  source              : %s" % src)
        for k in ("Content-Type", "Content-Disposition", "Content-Length"):
            print("  %-20s: %s" % (k, hget(dh, k)))
        print("  PDF 魔数            : %r  %s" % (db[:5], "√" if db[:5] == b"%PDF-" else "×"))
        print("  尾部有 %%EOF        : %s" % (b"%%EOF" in db[-4096:]))
        print("  字节数              : %d" % len(db))
        # inline 才是在浏览器里直接预览（而不是下载）
        cd = hget(dh, "Content-Disposition") or ""
        print("  inline 预览         : %s" % ("√" if "inline" in cd else "× " + cd))
    else:
        print("\n★ 该问题没有任何可点开的引用 —— 全是死链")


if __name__ == "__main__":
    main()
