#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""判定"判据库不一致"到底是内容不同还是只有序列化格式不同。"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = os.path.join(ROOT, "_中间产物", "_crit_server")

FILES = ["环境风险判据.json", "报告表结构.json", "标准引用清单.json"]

for n in FILES:
    lp = os.path.join(ROOT, "判据库", n)
    sp = os.path.join(TMP, n)
    if not (os.path.isfile(lp) and os.path.isfile(sp)):
        print("%-24s 文件不全，跳过" % n)
        continue
    a = json.loads(open(lp, encoding="utf-8").read())
    b = json.loads(open(sp, encoding="utf-8").read())
    ca = json.dumps(a, ensure_ascii=False, sort_keys=True)
    cb = json.dumps(b, ensure_ascii=False, sort_keys=True)
    ra = open(lp, encoding="utf-8").read()
    rb = open(sp, encoding="utf-8").read()
    print("=" * 74)
    print(n)
    print("  内容规范化后是否相同 :", ca == cb)
    print("  原始文本是否相同     :", ra == rb)
    print("  本地前 120 字符      : %r" % ra[:120])
    print("  线上前 120 字符      : %r" % rb[:120])
    # 行数差异能看出缩进不同
    print("  行数  本地 %d / 线上 %d" % (ra.count("\n"), rb.count("\n")))
