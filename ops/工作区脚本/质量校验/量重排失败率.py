#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量化重排失败率，并在失败时打印服务端 400 的具体原因。

做法：对多条真实问题，走一遍 Retriever 的召回→重排流程；
重排失败时，用同一批候选再发一次并打印 HTTP 错误详情。
"""
import json
import sys
import urllib.error
import urllib.request

sys.path.insert(0, "/data/fagui_rag")
import retriever as R  # noqa: E402

QS = [
    "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？",
    "一般工业固体废物贮存场 I 类场的防渗要求是什么？",
    "大气环境影响评价的评价等级是怎么判定的？",
    "生活垃圾焚烧烟气中二噁英的排放限值是多少？",
    "危险废物的鉴别标准是什么？",
    "危险废物焚烧的排污许可技术规范有哪些要求？",
    "污水处理厂恶臭污染物排放标准是多少？",
    "环境影响报告书编制依据有哪些？",
    "郑州市金水河综合整治工程的环境影响评价结论是什么？",
    "钢铁工业大气污染物排放限值是多少？",
]

r = R.Retriever()
ok = bad = 0
first_bad_detail = None
for q in QS:
    qv = r.embed(q)
    hits = r.search(qv, top_k=20)
    cands = [(i, s, r.chunks[i]) for i, s in hits]
    docs = [c[2]["text"] for c in cands]
    body = json.dumps({"model": "BGE-RERANK-V2-M3", "query": q, "documents": docs}).encode()
    req = urllib.request.Request(R.BGE_RERANK_URL, data=body,
                                headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            resp.read()
        ok += 1
        print(f"OK    {q[:34]}  (docs={len(docs)} 字符总数={sum(map(len, docs))})")
    except urllib.error.HTTPError as e:
        bad += 1
        detail = e.read().decode("utf-8", "replace")[:400]
        if first_bad_detail is None:
            first_bad_detail = (q, docs, detail)
        print(f"FAIL  {q[:34]}  HTTP {e.code}  (docs={len(docs)} 字符总数={sum(map(len, docs))})")
        print(f"      {detail[:200]}")

print(f"\n重排成功 {ok} / 失败 {bad}（共 {len(QS)}）")

if first_bad_detail:
    q, docs, detail = first_bad_detail
    print(f"\n首个失败样本：{q}")
    lens = sorted((len(d) for d in docs), reverse=True)
    print("  候选长度 top5:", lens[:5], " 总长:", sum(lens))
    # 逐条二分定位
    for i, d in enumerate(docs):
        b = json.dumps({"model": "BGE-RERANK-V2-M3", "query": q, "documents": [d]}).encode()
        rq = urllib.request.Request(R.BGE_RERANK_URL, data=b,
                                    headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(rq, timeout=60) as resp:
                resp.read()
        except urllib.error.HTTPError as e2:
            print(f"  单条 [{i}] 也失败 HTTP {e2.code}: "
                  f"{e2.read().decode('utf-8', 'replace')[:200]}")
            print(f"    前 100 字: {d[:100]!r}")
            break
    else:
        print("  逐条都通过 → 与候选组合有关（数量/总长）")
        for n in (2, 4, 8, 12, 16, 20):
            b = json.dumps({"model": "BGE-RERANK-V2-M3", "query": q,
                            "documents": docs[:n]}).encode()
            rq = urllib.request.Request(R.BGE_RERANK_URL, data=b,
                                        headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(rq, timeout=60) as resp:
                    resp.read()
                print(f"  前 {n} 条: OK")
            except urllib.error.HTTPError as e3:
                print(f"  前 {n} 条: HTTP {e3.code} "
                      f"总长={sum(len(x) for x in docs[:n])}")
                break
