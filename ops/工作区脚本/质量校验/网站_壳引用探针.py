#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""壳引用探针：检查线上问答是否把"网页导航壳"当作正文来源引用。

壳文档只有标准名/标准号/一两句摘要 + 导航文字，没有规范性内容。
如果这类文档被当正文引用，模型就只能靠常识补，专业性无从谈起。

用法（在服务器上跑，或本地指定 URL）：
  python3 网站_壳引用探针.py
  python3 网站_壳引用探针.py --url http://10.201.31.10:8011 "自定义问题"
"""
import argparse
import json
import os
import re
import sys
import urllib.request

NAV = re.compile(r"当前位置|热门搜索|点击进入|标准发布|标准解读|标准文本|标准修改与解释")
BUNDLE_ROOT = os.environ.get("BUNDLE_ROOT", "/data/fagui_rag/okf_bundles")

DEFAULT_QUESTIONS = [
    "制糖工业水污染物排放标准 GB 21909-2008 规定的排放限值是多少？",
    "环境空气质量标准 GB 3095-2012 中 PM10 年平均二级浓度限值是多少？",
    "海水水质标准 GB 3097-1997 对第一类海水水质的要求是什么？",
    "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？",
]


def local_text(source):
    """把 source 映射回 bundle 里的 md，返回正文字数；找不到返回 None。"""
    if not source:
        return None
    cands = [source]
    if source.startswith("/data/fagui_rag/okf_bundles/"):
        cands.append(source)
    else:
        cands.append(os.path.join(BUNDLE_ROOT, source.lstrip("/")))
    for c in cands:
        if c.endswith(".md") and os.path.isfile(c):
            try:
                return len(open(c, encoding="utf-8").read())
            except Exception:
                return None
    return None


def ask(url, q):
    body = json.dumps({"query": q, "top_k": 5}).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/hybrid_search",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8011")
    ap.add_argument("questions", nargs="*")
    a = ap.parse_args()
    qs = a.questions or DEFAULT_QUESTIONS

    shell_hits = total_hits = 0
    for q in qs:
        print("=" * 78)
        print("问:", q)
        try:
            d = ask(a.url, q)
        except Exception as e:
            print("  请求失败:", e)
            continue
        ans = (d.get("answer") or "").strip()
        print(f"答（前 260 字）: {ans[:260]}")
        srcs = d.get("sources") or []
        print(f"引用 {len(srcs)} 条:")
        for s in srcs:
            sp = s.get("source") or s.get("path") or ""
            ln = local_text(sp)
            flag = ""
            total_hits += 1
            if ln is not None and ln <= 1500:
                try:
                    t = open(sp, encoding="utf-8").read()
                    if len(NAV.findall(t)) >= 2:
                        flag = "  <<< 壳文档"
                        shell_hits += 1
                except Exception:
                    pass
            print(f"  - [{ln if ln is not None else '?'} 字] {sp[:110]}{flag}")
    print("=" * 78)
    print(f"引用总计 {total_hits} 条，其中壳文档 {shell_hits} 条 "
          f"({100.0*shell_hits/max(total_hits,1):.0f}%)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
