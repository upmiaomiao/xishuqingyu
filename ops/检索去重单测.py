#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""引用去重的单元测试（纯函数，不需要检索服务）。

被测：Retriever.diversify —— 同一 source 文档在引用列表中最多占 per_doc 条。
验证方式含**缺陷注入**：把上限调成 99（等于不去重）后，断言必须失败，
以证明这个测试真的能抓到"没去重"。

用法（本地或服务器均可）：python3 检索去重单测.py [被测定目录]
  被测定目录需能从其中 import retriever（默认 /data/fagui_rag）
"""
import sys

sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag")
from retriever import Retriever  # noqa: E402


def make(results_sources, top_k, per_doc):
    """构造候选：results 按相关度降序，元素是候选下标。

    sources 元素可以是字符串（文件名）或 dict（含 standard_id / source），
    后者用于验证"同一标准的多份文件也要合并计数"。
    """
    candidates = []
    for i, s in enumerate(results_sources):
        if isinstance(s, dict):
            meta = {"text": f"t{i}", "title": f"T{i}", **s}
        else:
            meta = {"source": s, "text": f"t{i}", "title": f"T{i}"}
        candidates.append((i, 0.5, meta))
    results = [{"index": i, "relevance_score": 1.0 - i * 0.01}
               for i in range(len(results_sources))]
    return Retriever.diversify(results, candidates, top_k, per_doc)


def count_per_source(picked, sources):
    c = {}
    for r in picked:
        s = sources[r["index"]]
        key = s if isinstance(s, str) else (s.get("standard_id") or s.get("source") or "")
        c[key] = c.get(key, 0) + 1
    return c


FAILED = []


def check(name, cond, detail=""):
    print(f"  {'OK  ' if cond else 'FAIL'} {name}{('  ' + detail) if detail else ''}")
    if not cond:
        FAILED.append(name)


print("用例 1：同一文档霸榜（5 条里 4 条同一文件）")
sources = ["A", "A", "A", "A", "B", "C", "D", "E"]
picked = make(sources, top_k=5, per_doc=2)
c = count_per_source(picked, sources)
print("     取到来源分布:", c)
check("返回条数仍为 top_k", len(picked) == 5, f"实际 {len(picked)}")
check("A 不超过 per_doc", c.get("A", 0) <= 2, f"A={c.get('A', 0)}")
check("引入了其它来源", len(c) >= 4, f"来源数 {len(c)}")
check("保持相关度降序", [r["index"] for r in picked] == sorted(r["index"] for r in picked))

print("\n用例 2：候选里只有 2 份文档（去重不能把结果变少）")
sources2 = ["A", "A", "A", "B", "B", "B"]
picked2 = make(sources2, top_k=5, per_doc=2)
check("仍返回 5 条", len(picked2) == 5, f"实际 {len(picked2)}")
c2 = count_per_source(picked2, sources2)
print("     来源分布:", c2)
# 语义：先严格按 per_doc 取（A、B 各 2 条），名额没满再放宽补齐到 top_k。
# 只有 2 个来源要凑 5 条，最终必然是 3+2 —— 这是"来源不足"时的合理放宽，
# 若强行不超上限就只能返回 4 条，反而少给模型一份依据。
check("前 4 条先按上限取满", c2.get("A", 0) >= 2 and c2.get("B", 0) >= 2, str(c2))
check("总数补足 top_k", sum(c2.values()) == 5, str(c2))

print("\n用例 3：per_doc=1（更严格的分散）")
sources3 = ["A", "A", "A", "B", "C", "D"]
picked3 = make(sources3, top_k=3, per_doc=1)
c3 = count_per_source(picked3, sources3)
print("     来源分布:", c3)
check("三份互不相同", len(c3) == 3 and max(c3.values()) == 1, str(c3))

print("\n用例 4：候选数少于 top_k")
picked4 = make(["A", "B"], top_k=5, per_doc=2)
check("返回 2 条不报错", len(picked4) == 2, f"实际 {len(picked4)}")

print("\n用例 5：同一标准的**多份不同文件**也要合并计数（破折号/空格差异）")
sid_cases = [
    {"standard_id": "HJ 1039—2019", "source": "a/生活垃圾焚烧/正文.md"},
    {"standard_id": "HJ 1039-2019", "source": "b/生活垃圾焚烧/副本.md"},
    {"standard_id": "HJ1039—2019", "source": "c/生活垃圾焚烧/公告.md"},
    {"standard_id": "HJ 1039—2019", "source": "d/生活垃圾焚烧/解读.md"},
    {"standard_id": "GB 18599-2020", "source": "e/一般工业固废.md"},
]
picked5 = make(sid_cases, top_k=3, per_doc=2)
c5 = count_per_source(picked5, sid_cases)
print("     引用取到的标准分布:", c5)
hj = sum(v for k, v in c5.items() if k.startswith("HJ") or k.startswith("SID:HJ"))
check("同一标准不超过 per_doc", hj <= 2, f"HJ1039 系列共 {hj} 条")
check("仍返回 3 条", len(picked5) == 3, f"实际 {len(picked5)}")

print("\n缺陷注入：把上限调成 99（等于不去重），用例 1 的断言必须失败")
injected = make(sources, top_k=5, per_doc=99)
ci = count_per_source(injected, sources)
caught = ci.get("A", 0) > 2
check("注入缺陷被测试抓住", caught, f"注入后 A={ci.get('A', 0)}（>2 才算抓住）")

print()
if FAILED:
    print(f"未通过 {len(FAILED)} 项: {FAILED}")
    sys.exit(1)
print("全部通过")
