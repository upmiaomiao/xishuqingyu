#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""即时冒烟：模拟一个用户此刻打开站点会做的四件事，逐项确认可用性。

对应关系：
  ① 打开页面          → GET /
  ② 问一个专业问题    → GET /hybrid_search（走 RAG + 图谱 + rerank）
  ③ 上传报告做审核    → /audit/api/run（真调模型）
  ④ 生成一份报告草稿  → /gen/api/health + /gen/api/outputs
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://10.201.31.10:8011"


def req(method, path, data=None, timeout=300):
    body = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else None
    h = {"Content-Type": "application/json"} if body else {}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    t0 = time.time()
    try:
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return resp.status, resp.read(), round(time.time() - t0, 1)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), round(time.time() - t0, 1)
    except Exception as e:                                     # noqa: BLE001
        return -1, str(e).encode(), round(time.time() - t0, 1)


def J(b):
    try:
        return json.loads(b.decode("utf-8"))
    except Exception:                                          # noqa: BLE001
        return None


def main():
    print("=" * 72)
    print("即时冒烟 @ %s" % time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 72)

    # ① 打开页面
    st, b, t = req("GET", "/")
    print("\n① 打开首页            HTTP %s  %d 字节  %.1fs" % (st, len(b), t))

    # ② 问一个专业问题
    q = "危险废物贮存污染控制标准有哪些要求"
    st, b, t = req("GET", "/hybrid_search?query=" + urllib.parse.quote(q))
    d = J(b) or {}
    srcs = d.get("sources") or []
    rr = [s for s in srcs if s.get("rerank_score") is not None]
    print("\n② 专业问答（RAG）     HTTP %s  %.1fs" % (st, t))
    print("   问题：%s" % q)
    print("   route=%s  来源 %d 条（其中带 rerank_score %d 条）"
          % (d.get("route"), len(srcs), len(rr)))
    print("   回答长度 %d 字" % len(d.get("answer") or ""))
    print("   回答开头：%s" % (d.get("answer") or "")[:90].replace("\n", " "))

    # ③ 上传报告做审核
    st, b, t = req("GET", "/audit/api/reports")
    reps = (J(b) or {}).get("reports") or []
    print("\n③ 报告审核            HTTP %s  可选报告 %d 份" % (st, len(reps)))
    if reps:
        name = reps[0]["name"]
        st, b, t = req("POST", "/audit/api/run?name=%s&use_llm=true" % urllib.parse.quote(name),
                       timeout=900)
        job = (J(b) or {}).get("job") or (J(b) or {}).get("id")
        print("   提交：%s → HTTP %s  job=%s  %.1fs" % (name[:34], st, str(job)[:12], t))
        for _ in range(60):
            st2, b2, _ = req("GET", "/audit/api/job/%s" % job)
            j = J(b2) or {}
            if j.get("status") in ("done", "failed", "error"):
                items = j.get("items") or j.get("结果") or []
                print("   状态=%s  审核项 %d 项  统计=%s"
                      % (j.get("status"), len(items), j.get("统计") or j.get("summary")))
                break
            time.sleep(1)

    # ④ 生成侧
    st, b, t = req("GET", "/gen/api/health")
    print("\n④ 报告编制            HTTP %s  %s" % (st, (J(b) or {}).get("ok")))
    st, b, t = req("GET", "/gen/api/outputs")
    print("   历史报告 %d 份" % len((J(b) or {}).get("files") or []))


if __name__ == "__main__":
    main()
