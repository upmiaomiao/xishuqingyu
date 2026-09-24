#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图片通路实测：现场照片专业研判（report=photo）、纯图提问、超大图 413、非法图片 400。"""
from __future__ import annotations

import base64
import json
import struct
import urllib.error
import urllib.request
import zlib

BASE = "http://10.201.31.10:8011"
OK, BAD = [], []


def check(n, c, d=""):
    (OK if c else BAD).append(n)
    print("  %s %s%s" % ("√" if c else "×", n, ("　" + str(d)[:170]) if d else ""))


def png(w=48, h=48, rgb=(120, 160, 200)) -> bytes:
    """手搓一张最小合法 PNG（不依赖 PIL）。"""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw))
            + chunk(b"IEND", b""))


def post(payload, timeout=240):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    r = urllib.request.Request(BASE + "/hybrid_search", data=body,
                               headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode()


def J(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return {}


data_url = "data:image/png;base64," + base64.b64encode(png()).decode()
print("测试图片：48×48 PNG，data URL 长度 %d 字符\n" % len(data_url))

print("[1] 非法图片格式 → 400")
st, b = post({"query": "看看这张图", "image": "http://example.com/a.png"})
check("非 data URL → 400", st == 400, "%s %s" % (st, J(b).get("detail")))

print("\n[2] data:image 但没有 base64 段 → 400")
st, b = post({"query": "看看", "image": "data:image/png,notbase64"})
check("缺 ;base64, → 400", st == 400, "%s %s" % (st, J(b).get("detail")))

print("\n[3] 超大图 → 413（上限 9,000,000 字符）")
big = "data:image/png;base64," + "A" * 9_000_001
st, b = post({"query": "看看", "image": big}, timeout=300)
check("超过上限 → 413 且提示压缩", st == 413 and "太大" in str(J(b).get("detail")),
      "%s %s" % (st, str(J(b).get("detail"))[:100]))

print("\n[4] 纯图提问（不写字）→ 应走识图再作答")
st, b = post({"image": data_url})
d = J(b)
check("纯图提问不返回 400（图片被接受）", st != 400, "HTTP %s" % st)
print("      HTTP %s route=%s image_note=%r answer=%s"
      % (st, d.get("route"), (d.get("image_note") or "")[:40], (d.get("answer") or "")[:80]))
if st == 502:
    print("      → 502 又是检索服务那条链（同缺陷③）")

print("\n[5] 现场照片专业研判 report=photo → 三态核验清单")
st, b = post({"query": "这张现场照片有什么问题？", "image": data_url, "report": "photo"})
d = J(b)
check("report=photo 有响应（非 400）", st != 400, "HTTP %s" % st)
ans = d.get("answer") or ""
print("      HTTP %s answer 长度 %d：%s" % (st, len(ans), ans[:150].replace("\n", " ")))
if st == 200:
    check("  研判答案里有三态用语（满足/不满足/无法判断 之一）",
          any(k in ans for k in ("满足", "无法判断", "不满足")), ans[:80])
else:
    check("  若不是 200，错误信息可读", bool(d.get("detail")), str(d.get("detail"))[:120])

print("\n==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
for x in BAD:
    print("  × %s" % x)
