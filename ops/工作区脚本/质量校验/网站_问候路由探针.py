#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""问候/身份类问题的流式拆分探针：确认 reasoning / answer 是否被正确分开。

背景：ThinkAnswerSplitter.feed() 在**没有 <think> 块**时不会调用 _process_answer，
于是整段输出（含 <answer>、【回答】等标记）都被当成 reasoning 发出，答案区为空。
本脚本用于在生产上验证该缺陷是否存在。
"""
import json
import sys

import httpx

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://10.201.31.10:8011"
QUESTIONS = ["你好", "你是谁？", "好的", "谢谢", "在吗"]

bad = 0
for q in QUESTIONS:
    ev = {"reasoning": "", "answer": "", "route": ""}
    with httpx.stream("POST", f"{BASE}/hybrid_search/stream",
                      json={"query": q, "history": []}, timeout=180) as r:
        e = d = None
        for line in r.iter_lines():
            s = line.strip()
            if s.startswith("event:"):
                e = s[6:].strip()
            elif s.startswith("data:"):
                d = s[5:].strip()
            elif s == "":
                if not e:
                    continue
                try:
                    p = json.loads(d) if d else None
                except Exception:
                    p = None
                if e == "reasoning":
                    ev["reasoning"] += p if isinstance(p, str) else ""
                elif e == "chunk":
                    ev["answer"] += p if isinstance(p, str) else ""
                elif e in ("meta", "done"):
                    ev["route"] = (p or {}).get("route", ev["route"])
                e = d = None

    leaked = [m for m in ("<answer>", "</answer>", "【回答】", "【分析过程】", "<think>", "</think>")
              if m in ev["answer"] or m in ev["reasoning"]]
    empty_answer = not ev["answer"].strip()
    flag = "❌" if (empty_answer or leaked) else "✅"
    if empty_answer or leaked:
        bad += 1
    print(f"{flag} Q={q!r} route={ev['route']} reasoning={len(ev['reasoning'])}字 "
          f"answer={len(ev['answer'])}字 泄漏标记={leaked}")
    print(f"     reasoning: {ev['reasoning'][:120].replace(chr(10), ' ')}")
    print(f"     answer   : {ev['answer'][:120].replace(chr(10), ' ')}")

print(f"\n结论：{'全部正常 ✅' if bad == 0 else f'{bad}/{len(QUESTIONS)} 题异常 ❌'}")
sys.exit(0 if bad == 0 else 1)
