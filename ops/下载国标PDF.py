#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 hcno 从国家标准全文公开系统下载标准全文（二进制安全；只读网络）。

用法：/home/test/fagui_serve/.venv/bin/python 下载国标PDF.py <hcno> [输出路径]
例：  下载国标PDF.py 2B827DAFB30501934A812F5F20AD7D17 /tmp/gb3095_2026.pdf
"""
from __future__ import annotations

import io
import sys
import urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")


def fetch(url: str, referer: str) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Referer": referer, "Accept": "*/*",
        "Accept-Language": "zh-CN,zh;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except Exception as exc:                                        # noqa: BLE001
        return 0, str(exc).encode("utf-8"), ""


def main() -> int:
    hcno = sys.argv[1] if len(sys.argv) > 1 else "2B827DAFB30501934A812F5F20AD7D17"
    out = sys.argv[2] if len(sys.argv) > 2 else "/tmp/gb_%s.pdf" % hcno[:10]
    info = "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=%s" % hcno
    st, page, _ = fetch(info, "https://openstd.samr.gov.cn/bzgk/gb/")
    print("详情页 HTTP %s，%d 字节" % (st, len(page)))
    txt = page.decode("utf-8", "replace")
    for key in ("在线预览", "下载", "showGb", "onlineRead", "viewGb"):
        i = txt.find(key)
        if i >= 0:
            print("   页面里出现「%s」→ %s" % (key, txt[max(0, i - 120):i + 120].replace("\n", " ")[:220]))

    for url in ("https://c.gb688.cn/bzgk/gb/showGb?type=download&hcno=%s" % hcno,
                "https://openstd.samr.gov.cn/bzgk/gb/showGb?type=download&hcno=%s" % hcno,
                "https://c.gb688.cn/bzgk/gb/showGb?type=online&hcno=%s" % hcno):
        st, body, ctype = fetch(url, info)
        head = body[:8]
        print("\n%s\n   HTTP %s ｜ %d 字节 ｜ %s ｜ 头 8 字节 %r"
              % (url, st, len(body), ctype, head))
        if st == 200 and head.startswith(b"%PDF"):
            io.open(out, "wb").write(body)
            print("   ✅ 已存 PDF → %s" % out)
            return 0
        if st == 200 and len(body) > 5000 and b"<html" not in head.lower():
            io.open(out, "wb").write(body)
            print("   ⚠️ 不是 PDF 但体积不小，已存 → %s（用 file 看看）" % out)
            return 0
        if body[:200]:
            print("   返回：%s" % body[:180].decode("utf-8", "replace").replace("\n", " "))
    print("\n❌ 三个端点都没拿到 PDF")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
