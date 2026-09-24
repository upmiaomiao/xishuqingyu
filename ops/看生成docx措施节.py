#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""C9 / C10-③ 真机取证：从生成任务日志 + 生成的 docx 正文里看结果。

为什么要看这两处：
  · 任务结果 JSON 只有 判定/校验/自审/file —— **叙述不在里面**，在 docx 里；
  · `gen_routes` 在 ③生成 这一步会记一行「事实表 N 条；叙述 M 小节；被出处闸门剔除 D 句」，
    这行正好能验证 C9（有措施 / 没措施时小节的差别）与事实表条数（C10-③）。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
import zipfile

BASE = "http://127.0.0.1:8011/gen/api"
SEC = "运营期环境影响和保护措施概述"
WORDS = ("布袋除尘", "喷淋塔", "活性炭", "SCR", "SNCR", "脱硫", "MBR", "反渗透",
         "隔声", "减振", "危废暂存", "抑尘", "洒水")


def docx_text(path: str) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    xml = re.sub(r"</w:p>", "\n", xml)
    txt = re.sub(r"<[^>]+>", "", xml)
    return txt.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")


def main() -> int:
    for p in sys.argv[1:]:
        print("=" * 88)
        print(os.path.basename(p))
        d = json.load(open(p, encoding="utf-8"))
        print("  状态=%s 模型=%s 耗时=%ss 文件=%s" % (d.get("status"), d.get("模型"),
                                                d.get("secs"), d.get("file")))
        print("  ── 任务日志：")
        for line in (d.get("log") or []):
            s = json.dumps(line, ensure_ascii=False) if not isinstance(line, str) else line
            if any(k in s for k in ("事实表", "小节", "剔除", "叙述", "措施", "单位", "折合")):
                print("     %s" % s[:220])
        jid = d.get("id")
        out = "/home/test/%s.docx" % os.path.splitext(os.path.basename(p))[0]
        try:
            with urllib.request.urlopen(BASE + "/download/" + str(jid), timeout=300) as r:
                open(out, "wb").write(r.read())
            print("  ── docx：%s（%d 字节）" % (out, os.path.getsize(out)))
        except Exception as exc:                                # noqa: BLE001
            print("  ── 下载失败：%s" % exc)
            continue
        txt = docx_text(out)
        for marker in ("四、主要环境影响和保护措施", "工具不编措施：请填报",
                       "活性炭吸附装置", "附：叙述与剔除记录", "布袋除尘"):
            print("     含「%s」：%s" % (marker, marker in txt))
        i = txt.find("四、主要环境影响和保护措施")
        if i >= 0:
            print("     ── 四、… 区段：")
            print("     %s" % txt[i:i + 420].replace("\n", " ⏎ ")[:420])
        j = txt.find("附：叙述与剔除记录")
        if j >= 0:
            print("     ── 叙述与剔除记录（出处闸门凭据）：")
            print("     %s" % txt[j:j + 700].replace("\n", " ⏎ ")[:700])
        print("     全文措施词统计：%s" % {w: txt.count(w) for w in WORDS if txt.count(w)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
