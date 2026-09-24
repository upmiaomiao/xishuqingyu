#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""决定性实验：P6 版 ingest_okf 与线上版，对**普通文档**切出来的块是否逐字相同？

为什么这一步是 P6 能否上线的分水岭：
  · 若**相同** ⇒ 只有"表格类"文档的切块会变 ⇒ 只需重切/重嵌**受影响的那些 bundle**，
    线上 26 万块的向量可以逐字节沿用（09-22 09:39 那次索引更新就是这么做的，见 meta.note）；
  · 若**不同** ⇒ 切块规则对全库都变了 ⇒ 26 万块要全部重嵌（小时级 + 索引 1.5 GB 重建），
    那是另一量级的动作，必须先报告再干。

做法：把两个版本的 chunk 入口都加载进来，对同一批 bundle 跑一遍，逐块比对。
不写任何文件、不联网、不调模型。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 试切块等价性.py
"""
from __future__ import annotations

import importlib.util
import io
import random
import re
import sys
from pathlib import Path

LIVE = "/data/fagui_rag/ingest_okf.py"
P6 = "/home/test/ingest_p6.py"
BUNDLES = Path("/data/fagui_rag/okf_bundles")
SAMPLE_N = 40


def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)          # 需要有 __main__ 守卫，否则会跑主流程
    return mod


def defs(src: str) -> list:
    return re.findall(r"^def (\w+)\(([^)]*)\)", src, re.M)


def main() -> int:
    ls, ps = io.open(LIVE, encoding="utf-8").read(), io.open(P6, encoding="utf-8").read()
    print("线上版 %d 行，函数：" % (ls.count("\n") + 1))
    for n, a in defs(ls):
        print("   %s(%s)" % (n, a[:60]))
    print("\nP6 版 %d 行，函数：" % (ps.count("\n") + 1))
    for n, a in defs(ps):
        print("   %s(%s)" % (n, a[:60]))

    lv, p6 = load(LIVE, "ingest_live"), load(P6, "ingest_p6")
    for tag, mod in (("线上", lv), ("P6", p6)):
        print("%s 有 chunk_by_paragraph：%s ｜ 有 split_okf：%s ｜ 有 normalize_body：%s"
              % (tag, hasattr(mod, "chunk_by_paragraph"), hasattr(mod, "split_okf"),
                 hasattr(mod, "normalize_body")))

    # 抽样：一半含死链表格、一半不含；覆盖大小档
    allmd = sorted(BUNDLES.rglob("*.md"))
    random.seed(20260922)
    withdead = [p for p in allmd if "![](images/" in io.open(p, encoding="utf-8", errors="replace").read()]
    nodead = [p for p in allmd if p not in set(withdead)]
    sample = random.sample(withdead, min(SAMPLE_N // 2, len(withdead))) + \
        random.sample(nodead, min(SAMPLE_N // 2, len(nodead)))
    print("\n抽样 %d 份（含死链表 %d ／ 普通 %d）"
          % (len(sample), min(SAMPLE_N // 2, len(withdead)), min(SAMPLE_N // 2, len(nodead))))

    same = diff = err = 0
    for p in sample:
        t = io.open(p, encoding="utf-8", errors="replace").read()
        try:
            fm, body = lv.split_okf(t) if hasattr(lv, "split_okf") else ({}, t)
            a = lv.chunk_by_paragraph(lv.normalize_body(body))
            fm2, body2 = p6.split_okf(t)
            b = p6.chunk_by_paragraph(p6.normalize_body(body2))
        except Exception as exc:                                    # noqa: BLE001
            err += 1
            print("   ! %s → %s" % (p.name[:44], exc))
            continue
        if a == b:
            same += 1
        else:
            diff += 1
            if diff <= 5:
                print("   × %s：线上 %d 块 / P6 %d 块" % (p.name[:44], len(a), len(b)))
                for i, (x, y) in enumerate(zip(a, b)):
                    if x != y:
                        print("       第 %d 块不同：" % i)
                        print("         线上：%s" % x[:110].replace("\n", " "))
                        print("         P6　：%s" % y[:110].replace("\n", " "))
                        break

    print("\n" + "=" * 84)
    print("逐字相同：%d ／ 不同：%d ／ 出错：%d" % (same, diff, err))
    print("结论：%s" % ("两个版本对这批文档切块**完全一致** → 可增量上线（只重切受影响文档）"
                      if diff == 0 and err == 0 else
                      "切块有差异 → 需要看清差异来自表格逻辑还是全局规则，再决定量级"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
