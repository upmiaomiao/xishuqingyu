#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从"国家标准全文公开系统"取强制性国标全文（这里要的是 GB 3095—2026）。

思路：先按标准号搜索列表页，从结果里抠出 hcno，再请求下载端点。
只读网络，不写任何语料/索引文件。

用法：/home/test/fagui_serve/.venv/bin/python 取国标全文.py [标准号片段]
"""
from __future__ import annotations

import io
import re
import sys
import urllib.parse
import urllib.request

Q = sys.argv[1] if len(sys.argv) > 1 else "GB 3095"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122 Safari/537.36")


def get(url: str, referer: str = "") -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer,
                                               "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
            try:
                return r.status, raw.decode("utf-8")
            except UnicodeDecodeError:
                return r.status, raw.decode("gbk", "replace")
    except Exception as exc:                                        # noqa: BLE001
        return 0, "ERR %s" % exc


def main() -> int:
    q = urllib.parse.quote(Q)
    url = ("https://openstd.samr.gov.cn/bzgk/gb/std_list?p.p1=0&p.p90=circulation_date"
           "&p.p91=desc&p.p2=" + q)
    st, html = get(url)
    print("列表页 %s → HTTP %s，%d 字节" % (url, st, len(html)))
    if st != 200:
        print(html[:300])
        return 1
    # 列表里的每个标准都带 newGbInfo?hcno=xxxx
    rows = re.findall(r"newGbInfo\?hcno=([0-9A-Za-z]+)[^>]*>([^<]{0,80})", html)
    seen = []
    for hc, name in rows:
        if hc not in [s[0] for s in seen]:
            seen.append((hc, name.strip()))
    print("候选 %d 个：" % len(seen))
    for hc, name in seen[:8]:
        print("   hcno=%s  %s" % (hc, name[:70]))
    if not seen:
        # 有的页面把标准号和 hcno 分在不同位置，退而求其次打印可疑片段
        for m in re.finditer(r"GB[^<]{0,20}3095[^<]{0,30}", html):
            print("   片段：%s" % m.group(0)[:80])
        return 1

    hc = seen[0][0]
    info = "https://openstd.samr.gov.cn/bzgk/gb/newGbInfo?hcno=%s" % hc
    st2, page = get(info)
    print("\n详情页 %s → HTTP %s" % (info, st2))
    for m in re.finditer(r"(showGb\?type=\w+&hcno=[0-9A-Za-z]+|/bzgk/gb/[^\"']*onlineRead[^\"']*)", page):
        print("   可能的阅读/下载入口：%s" % m.group(1))
    # 试下载
    dl = "https://c.gb688.cn/bzgk/gb/showGb?type=download&hcno=%s" % hc
    st3, body = get(dl, referer=info)
    print("\n下载端点 → HTTP %s，%d 字节" % (st3, len(body)))
    if st3 == 200 and len(body) > 20000:
        out = "/tmp/" + Q.replace(" ", "_") + ".pdf"
        io.open(out, "wb").write(body.encode("latin-1", "ignore") if isinstance(body, str) else body)
        print("   已存 → %s（若是 PDF，file 一下确认）" % out)
    else:
        print("   没拿到二进制：%s" % body[:200].replace("\n", " "))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
