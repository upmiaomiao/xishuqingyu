#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判据库数字化 (3)：报告表编制技术指南（污染影响类）+ 有毒有害大气污染物名录。

指南：MEE 的 PDF 附件 → 文本 + find_tables → 找"专项评价"设置条件表
名录：公告页正文 → 抽取污染物清单
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request

import fitz

UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120 Safari/537.36"}
OUT = "/data/fagui_rag/criteria"
PDFS = [
    ("报告表编制技术指南（污染影响类）试行",
     "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk05/202101/W020210104371003931528.pdf"),
    ("报告表编制技术指南（生态影响类）试行",
     "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk05/202101/W020210104371004465028.pdf"),
]
LIST_URL = "https://www.mee.gov.cn/xxgk2018/xxgk/xxgk01/201901/t20190131_691779.html"


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def do_pdfs():
    os.makedirs(OUT, exist_ok=True)
    for name, url in PDFS:
        dest = os.path.join(OUT, name + ".pdf")
        try:
            raw = fetch(url)
        except Exception as e:
            print(f"[失败] {name}: {e}")
            continue
        if not raw.startswith(b"%PDF"):
            print(f"[跳过] {name}: 不是 PDF（{len(raw)} 字节, 头 {raw[:6]!r}）")
            continue
        open(dest, "wb").write(raw)
        d = fitz.open(dest)
        text = "".join(d[i].get_text() for i in range(d.page_count))
        print(f"\n=== {name}  {d.page_count} 页  {len(text):,} 字")
        # 专项评价设置条件
        for m in list(re.finditer(r"专项评价", text))[:6]:
            seg = re.sub(r"\s+", " ", text[max(0, m.start() - 120): m.start() + 260])
            print(f"   …{seg}…")
        tabs = []
        for pno in range(d.page_count):
            try:
                t = d[pno].find_tables()
            except Exception:
                continue
            if t and t.tables:
                for tb in t.tables:
                    rows = tb.extract()
                    if rows and max(len(r) for r in rows) >= 2:
                        tabs.append((pno + 1, rows))
        print(f"   find_tables 命中 {len(tabs)} 张")
        keep = []
        for pno, rows in tabs:
            flat = " ".join(str(c) for r in rows for c in r if c)
            if "专项评价" in flat or "设置" in flat or "大气" in flat:
                keep.append({"page": pno, "rows": [[("" if c is None else re.sub(r"\s+", " ", str(c)))
                                                    for c in r] for r in rows]})
        if keep:
            print(f"   与专项评价相关的表 {len(keep)} 张，示例：")
            for t in keep[:2]:
                print(f"     p{t['page']}:")
                for r in t["rows"][:8]:
                    print("       | " + " | ".join(c[:22] for c in r))
        json.dump(keep, open(os.path.join(OUT, name + "_专项评价表.json"), "w",
                             encoding="utf-8"), ensure_ascii=False, indent=1)
        d.close()


def do_list():
    html = fetch(LIST_URL).decode("utf-8", "replace")
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    body = re.sub(r"(?s)<[^>]+>", " ", body)
    body = re.sub(r"&nbsp;?", " ", body)
    body = re.sub(r"\s+", " ", body)
    i = body.find("附件")
    j = body.find("有毒有害大气污染物名录", i)
    seg = body[j: j + 900] if j > 0 else body[i: i + 900]
    print("\n=== 有毒有害大气污染物名录（2018年）正文片段")
    print(seg)
    # 抓取形如 "1. 二氯甲烷" 或表格里的序号+名称
    nums = re.findall(r"(\d{1,2})\s*[.、]?\s*([\u4e00-\u9fff（）()A-Za-z0-9,，\-]{2,20})", seg)
    print("\n   解析出的候选项:", nums[:20])
    json.dump({"raw": seg, "parsed": nums},
              open(os.path.join(OUT, "有毒有害大气污染物名录2018.json"), "w",
                   encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    do_pdfs()
    do_list()
