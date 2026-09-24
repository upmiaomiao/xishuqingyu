#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查清「找不到原文 PDF」到底是文件真不在，还是路径对不上。

背景：界面上点「查看原文」会弹出一坨 JSON：
    {"ok":false,"code":"F_DOC_NOT_FOUND","message":"未找到原文 PDF：环评报告/…拆解项目环境影响报告.pdf"}
这正是我一直记着的 [009] 死链。在做友好界面之前必须先确定病因 ——
如果只是 .md 名字和 .pdf 名字对不上，那正确的修法是**修数据**，
而不是把错误包装得好看一点。

要回答：
  ① 索引里那条 source（…md）在磁盘上存在吗？
  ② 按服务端的换算规则推出来的 .pdf 存在吗？
  ③ 磁盘上有没有名字相近、其实就是同一个文件的 PDF？（大小写、空格、全半角、后缀）
  ④ 有多少条索引是这种对不上的？是个例还是普遍问题？
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"

# 界面上报错的那条
TARGET = ("环评报告/中华人民共和国生态环境部 - 2023 - 江苏苏州市物资再生有限公司"
          "报废机动车机械化拆解项目环境影响报告")


def get(path: str) -> tuple[int, str, str]:
    req = urllib.request.Request(BASE + path)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.headers.get("Content-Type", ""), r.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.read(2000).decode("utf-8", "replace")
    except Exception as e:                                          # noqa: BLE001
        return 0, "", str(e)


print("=" * 92)
print("一、直接请求界面上那条 .md 对应的 /doc")
print("=" * 92)
for suffix in (".md", ".pdf"):
    src = TARGET + suffix
    st, ct, body = get("/doc?source=" + urllib.parse.quote(src))
    print("  source=%s" % (src[-40:]))
    print("     -> HTTP %s  %s" % (st, ct))
    print("     -> %s" % body[:300].replace("\n", " "))

print()
print("=" * 92)
print("二、这条 source 在检索结果里长什么样（不猜，打真的检索接口）")
print("=" * 92)
q = "苏州 报废机动车 拆解 环境影响报告"
req = urllib.request.Request(
    BASE + "/hybrid_search/stream",
    data=json.dumps({"query": q, "history": [], "image": None, "report": None},
                    ensure_ascii=False).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
sources = []
with urllib.request.urlopen(req, timeout=300) as r:
    ev = data = ""
    for line_b in r:
        line = line_b.decode("utf-8").rstrip("\n")
        if line.startswith("event:"):
            ev = line[6:].strip()
        elif line.startswith("data:"):
            data += line[5:].strip()
        elif line == "" and ev:
            if ev == "meta":
                try:
                    sources = json.loads(data).get("sources") or []
                except Exception:                                  # noqa: BLE001
                    pass
            ev = data = ""
print("  检索到 %d 条资料" % len(sources))
interesting = [s for s in sources if "环评" in str(s.get("source", "")) or "环评" in str(s.get("title", ""))]
print("  其中标题或来源含「环评」的：%d 条" % len(interesting))
for s in (interesting or sources)[:6]:
    print("    [%s] %s" % (s.get("index"), str(s.get("title", ""))[:60]))
    print("         source=%r" % s.get("source"))
    print("         doc_type=%r status=%r" % (s.get("doc_type"), s.get("status")))
