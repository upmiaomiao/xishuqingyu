#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给"20 条实跑结果"打分：用项目里同款 flash 档模型当裁判（与 v5 焚烧测试同口径）。

维度（1-5，越大越好）：
  correctness 正确性 / coverage 覆盖 / actionability 可操作性
  grounding   有据（结论能否在引用来源或题目已知事实里找到支撑）
  boundary    边界（有没有编造题目与引用里都没有的具体数值；没编造=5）
另出：fabrications（可疑编造点）、data_gap（是否因语料缺数值而答不出）、
      answerable（所需数值能否从引用里得到）、brief（一句话点评）。

用法：python 评20条.py [--only 序号,序号]
输入：_工作记录/实跑20条_输出.jsonl
输出：_工作记录/实跑20条_评分.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
IN = WS / "_工作记录" / "实跑20条_输出.jsonl"
OUT = WS / "_工作记录" / "实跑20条_评分.jsonl"
D_RAW = WS / "_工作记录" / "_评20条_原始输出.jsonl"
MODEL = "deepseek-v4-flash-guan"

RUBRIC = """你是生态环境与垃圾焚烧发电领域的评审专家。下面给你：一道专业题、网站检索到的引用来源清单、网站给出的回答。
请只依据给定材料严格评分，别被篇幅和语气影响。每项 1-5 分（5 最好）：
- correctness 正确性：技术判断与法规结论是否正确
- coverage 覆盖：题目问到的每一问是否都答到
- actionability 可操作性：现场人员能否照此执行
- grounding 有据：结论能否在【引用来源】或【题目已知事实】里找到支撑
- boundary 边界：是否出现题目与引用里都没有的具体数值/百分位/统计量。完全没有编造 = 5
另外给出：
- fabrications：可疑编造点（原文片段，最多 5 条；没有就空数组）
- data_gap：回答是否说明了「资料里没有该数值/表格，无法给出」这类情况（true/false）
- answerable：本题所需的关键数值或结论，能否从引用来源中得到（true/false）
- brief：一句话点评（不超过 60 字）
只输出一个 JSON 对象，不要解释、不要代码块。"""


def dotenv(key: str) -> str | None:
    p = WS / ".env"
    if not p.is_file():
        return None
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def client() -> tuple[str, str]:
    key = os.environ.get("OPENAI_API_KEY") or dotenv("OPENAI_API_KEY")
    base = os.environ.get("OPENAI_BASE_URL") or dotenv("OPENAI_BASE_URL")
    if not key or not base:
        sys.exit("缺少 OPENAI_API_KEY / OPENAI_BASE_URL（环境变量或根 .env）")
    return key, base.rstrip("/")


def call(key: str, base: str, prompt: str, timeout: float = 600.0) -> tuple[str, str]:
    """返回 (content, finish_reason)。注意：flash 档会先想再答，max_tokens 给小了会把 JSON 截断。"""
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 12000,
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode())
    ch = d["choices"][0]
    return ch["message"].get("content") or "", ch.get("finish_reason") or ""


def extract_json(t: str) -> dict | None:
    t = re.sub(r"^```(?:json)?|```$", "", t.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None

    key, base = client()
    rows = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if only is None or r["序号"] in only]
    print(f"评审 {len(rows)} 条（模型 {MODEL}）\n" + "=" * 100)

    out = []
    raws: list[dict] = []
    for r in rows:
        if r.get("error"):
            out.append({**{k: r[k] for k in ("序号", "题型", "语言")}, "跳过": r["error"]})
            print(f"  [跳过] {r['序号']} {r['error']}")
            continue
        src_txt = "\n".join(f"- {s}" for s in (r.get("引用来源") or [])[:20]) or "（无引用）"
        ans = r.get("答案") or ""
        t0 = time.time()
        raw = ""
        j = {}
        err = ""
        for attempt in (1, 2):     # 第一次失败就缩短答案重试（长答案更容易把 JSON 截断）
            try:
                lim = 8000 if attempt == 1 else 4000
                p = (f"{RUBRIC}\n\n【题目】\n{r['题目'][:3000]}\n\n【引用来源清单】\n{src_txt}\n\n"
                     f"【网站回答】\n{ans[:lim]}\n")
                raw, fin = call(key, base, p)
                j = extract_json(raw) or {}
                if j:
                    err = ""
                    break
                err = f"判分输出不是 JSON（finish_reason={fin}，长度 {len(raw)}）"
            except Exception as e:  # noqa: BLE001
                j, err = {}, f"{type(e).__name__}: {str(e)[:120]}"
            if attempt == 1:
                raws.append({"序号": r["序号"], "原始输出": raw[:4000], "错误": err})
        dt = time.time() - t0
        dims = {k: j.get(k) for k in
                ("correctness", "coverage", "actionability", "grounding", "boundary")}
        got = [v for v in dims.values() if isinstance(v, (int, float))]
        rec = {**{k: r[k] for k in ("序号", "题型", "语言", "答案字数", "引用条数", "依据类条数",
                                   "题目中的标准号", "引用里命中的标准号", "回避表述", "数值个数")},
               **dims, "均分": round(sum(got) / len(got), 2) if got else None,
               "fabrications": j.get("fabrications") or [],
               "data_gap": j.get("data_gap"), "answerable": j.get("answerable"),
               "brief": (j.get("brief") or "")[:120], "判分错误": err, "判分耗时s": round(dt, 1)}
        out.append(rec)
        print(f"  [{rec['序号']:>2}] {rec['题型'][:12]:<12} 正确{rec['correctness']} 覆盖{rec['coverage']} "
              f"可操作{rec['actionability']} 有据{rec['grounding']} 边界{rec['boundary']} "
              f"均分{rec['均分']} 编造{len(rec['fabrications'])} data_gap={rec['data_gap']} "
              f"| {rec['brief'][:40]}")

    OUT.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out), encoding="utf-8")
    if raws:
        rb = D_RAW
        rb.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in raws), encoding="utf-8")
        print(f"\n⚠️ {len(raws)} 条第一次判分失败，原始输出留档 → {rb.relative_to(WS)}")
    scored = [o for o in out if o.get("均分")]
    if scored:
        print("\n" + "=" * 100)
        for k in ("correctness", "coverage", "actionability", "grounding", "boundary"):
            vals = [o[k] for o in scored if isinstance(o.get(k), (int, float))]
            print(f"  平均 {k:<14}{sum(vals)/len(vals):.2f}")
        print(f"  平均总分　　　{sum(o['均分'] for o in scored)/len(scored):.2f}")
        print(f"  data_gap=True 的 {sum(1 for o in scored if o['data_gap'])} 条；"
              f"answerable=False 的 {sum(1 for o in scored if o['answerable'] is False)} 条；"
              f"有编造指控的 {sum(1 for o in scored if o['fabrications'])} 条")
    print(f"\n→ {OUT.relative_to(WS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
