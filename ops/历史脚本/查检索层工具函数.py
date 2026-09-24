#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索层改造：纯函数单测（不需要索引、不连服务，纯本地跑）。

查两件事：
  ① doc_key 是否能把"同一份文件的副本"归成一个键 —— 线上实测到的三种形态；
  ② doc_key **不会**把真正不同的文档误并（反向断言）；
  ③ auth_need 的问题分类是否符合预期（含反向：案例类问题不许要 3 条依据）。
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SRC = Path(r"D:\项目\中节能\0911训练\服务器会话\服务端\rag\retriever.py")
spec = importlib.util.spec_from_file_location("retriever_new", SRC)
m = importlib.util.module_from_spec(spec)
# 只取纯函数，不实例化 Retriever（那要加载 1GB 索引）
spec.loader.exec_module(m)

ok = fail = 0
def say(cond: bool, msg: str) -> None:
    global ok, fail
    if cond:
        ok += 1
        print(f"  ✅ {msg}")
    else:
        fail += 1
        print(f"  ❌ {msg}")

print("===== ① 副本必须归并（线上实测到的三种形态）=====")
pairs = [
    ("环评报告/环评气化80t 宜川县.md", "环评报告/环评气化80t 宜川县 copy.md"),
    ("环评报告/济宁市生活垃圾焚烧发电二期改扩建项目环境影响报告书.md",
     "环评报告/济宁市生活垃圾焚烧发电二期改扩建项目环境影响报告书 copy.md"),
    ("环评报告/x电梯配件有限公司电梯配件生产新建项目.md",
     "环评报告/x电梯配件有限公司电梯配件生产新建项目环境影响报告.md"),
    ("环评报告/某项目（1）.md", "环评报告/某项目.md"),
    ("环评报告/某项目 - 副本.md", "环评报告/某项目.md"),
    ("环评报告/山东管网东干线天然气管道工程（平度-临沂段）环评报告书全本.md",
     "环评报告/山东管网东干线天然气管道工程（平度-临沂段）环评报告书.md"),
]
for a, b in pairs:
    ka, kb = m.doc_key(a), m.doc_key(b)
    say(ka == kb, f"归并 {a.split('/')[-1][:34]} ↔ {b.split('/')[-1][:34]}  →  {ka}")

print("\n===== ② 反向：不同文档不许误并 =====")
diff = [
    ("环评报告/甲项目.md", "环评报告/乙项目.md"),
    ("环评报告/某公司一期项目.md", "环评报告/某公司二期项目.md"),
    ("生态环境标准规范/一般工业固体废物贮存和填埋污染控制标准 GB 18599－2020.md",
     "生态环境标准规范/生活垃圾焚烧污染控制标准 GB 18485-2014.md"),
    ("环评报告/某项目.md", "生态环境标准规范/某项目.md"),
]
for a, b in diff:
    say(m.doc_key(a) != m.doc_key(b), f"不误并 {a.split('/')[-1][:30]} ✗ {b.split('/')[-1][:30]}")

print("\n===== ③ 短名保护：不许剥成空键、更不许把不同文件剥成同一个键 =====")
say(m.doc_key("环评报告/环评报告.md") != m.doc_key("环评报告/环评报告表.md"),
    "「环评报告.md」与「环评报告表.md」不同键（短名不剥尾巴）")
say(not m.doc_key("环评报告/环评报告.md").endswith("|"),
    "「环评报告.md」不会剥成空键")
say(m.doc_key("生态环境标准规范/HJ 2.1-2016 总纲.md") != m.doc_key("生态环境标准规范/HJ 2.2-2018 大气.md"),
    "HJ 2.1 与 HJ 2.2 不同键（标准语料没有 standard_id 参与，全靠文件名，这里确认真能分开）")

print("\n===== ④ 问题意图识别 =====")
cases = [
    ("二噁英的排放限值是多少？", 3, "含'限值' → 要 3 条依据"),
    ("GB 18599 一般工业固体废物贮存的标准要求", 3, "含标准号 → 要 3 条依据"),
    ("一般工业固体废物贮存场 I 类场的防渗要求是什么？", 3, "含'要求' → 要 3 条依据"),
    ("排污许可证的有效期是多久？", 3, "含'有效期' → 要 3 条依据"),
    ("济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？", 1, "案例类 → 只要 1 条依据"),
    ("这家公司的生产工艺是什么？", 1, "案例类 → 只要 1 条依据"),
    ("你好，介绍一下你自己", 2, "普通问题 → 默认 2 条依据"),
]
for q, exp, why in cases:
    got = m.auth_need(q)
    say(got == exp, f"「{q[:28]}」→ {got}（期望 {exp}，{why}）")

print("\n===== ⑤ 反向：案例类问题不许被塞 3 条依据 =====")
for q in ["济宁市生活垃圾焚烧发电二期改扩建项目的主要环境问题是什么？",
          "江苏苏州物资再生有限公司这个项目的建设内容是什么？"]:
    say(m.auth_need(q) < 3, f"「{q[:26]}」→ {m.auth_need(q)} < 3")

print(f"\n==== 通过 {ok} / 失败 {fail} ====")
sys.exit(1 if fail else 0)
