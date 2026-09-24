#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 20 条实跑结果打分（v2：把**引用正文**一起给裁判，才能真判"有据/编造"）。

输入：_工作记录/实跑20条_输出v2.jsonl
输出：_工作记录/实跑20条_评分v2.jsonl（+ 失败时原始输出留档）

维度：correctness/coverage/actionability/grounding/boundary，各 1-5；另出
      fabrications、data_gap、answerable、brief。
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
IN = WS / "_工作记录" / "实跑20条_输出v2.jsonl"
OUT = WS / "_工作记录" / "实跑20条_评分v2.jsonl"
RAW = WS / "_工作记录" / "_评20条v2_原始输出.jsonl"
MODEL = "deepseek-v4-flash-guan"
DIMS = ("correctness", "coverage", "actionability", "grounding", "boundary")

RUBRIC = """你是生态环境与垃圾焚烧发电领域的评审专家。材料包含：一道专业题、【检索到的引用来源（含正文片段）】、【网站回答】。
请严格按给定材料评分，别被篇幅和语气影响。每项 1-5 分（5 最好）：
- correctness 正确性：技术判断与法规结论是否正确
- coverage 覆盖：题目问到的每一问是否都答到
- actionability 可操作性：现场人员能否照此执行
- grounding 有据：答案里的条款号、限值、数据能否在【引用来源】或【题目已知事实】里找到（找不到就扣分）
- boundary 边界：是否出现引用与题目里都没有的具体数值/条款/结论。完全没有 = 5
另给：
- fabrications：可疑编造点（原文片段，最多 5 条；没有就空数组）
- data_gap：回答是否说明了「资料里没有该数值/条款」这类情况（true/false）
- answerable：本题所需的关键数值或结论能否从引用来源中得到（true/false）
- brief：一句话点评（<=60 字）
只输出一个 JSON 对象，不要解释、不要代码块。"""


def dotenv(key: str) -> str | None:
    p = WS / ".env"
    for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.strip().startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return None


def call(key: str, base: str, prompt: str, timeout: float = 900.0) -> tuple[str, str]:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0, "max_tokens": 16000}).encode()
    req = urllib.request.Request(f"{base}/chat/completions", data=body,
                                headers={"Content-Type": "application/json",
                                         "Authorization": f"Bearer {key}"})
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


def src_block(sources: list[dict], per: int) -> str:
    out = []
    for s in sources:
        head = (f"[{s.get('index')}] {s.get('title')}｜类型={s.get('doc_type')}"
                f"｜状态={s.get('status') or '—'}｜标准号={s.get('standard_id') or '—'}"
                f"｜rerank={s.get('rerank_score')}")
        body = " ".join((s.get("text") or "").split())[:per]
        out.append(f"{head}\n    {body}")
    return "\n".join(out) or "（无引用）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None

    key = os.environ.get("OPENAI_API_KEY") or dotenv("OPENAI_API_KEY")
    base = (os.environ.get("OPENAI_BASE_URL") or dotenv("OPENAI_BASE_URL")).rstrip("/")
    if not key or not base:
        sys.exit("缺少 OPENAI_API_KEY / OPENAI_BASE_URL")

    rows = [json.loads(l) for l in IN.read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if only is None or r["序号"] in only]
    print(f"评审 {len(rows)} 条（{MODEL}，带引用正文）\n" + "=" * 104, flush=True)

    out, raws = [], []
    for r in rows:
        if r.get("error"):
            out.append({"序号": r["序号"], "题型": r["题型"], "跳过": r["error"]})
            print(f"  [跳过] {r['序号']} {r['error']}", flush=True)
            continue
        ans = r.get("答案") or ""
        t0 = time.time()
        j, err, raw = {}, "", ""
        for attempt in (1, 2):
            per = 900 if attempt == 1 else 450
            prompt = (f"{RUBRIC}\n\n【题目】\n{r['题目'][:3000]}\n\n【引用来源】\n"
                      f"{src_block(r.get('引用') or [], per)}\n\n【网站回答】\n{ans[:9000]}\n")
            try:
                raw, fin = call(key, base, prompt)
                j = extract_json(raw) or {}
            except Exception as e:  # noqa: BLE001
                j, raw, fin = {}, "", f"{type(e).__name__}"
                err = f"{type(e).__name__}: {str(e)[:120]}"
            if j:
                err = ""
                break
            if not err:
                err = f"判分输出不是 JSON（finish_reason={fin}，长度 {len(raw)}）"
            if attempt == 1:
                raws.append({"序号": r["序号"], "原始输出": raw[:4000], "错误": err})
        dt = time.time() - t0
        dims = {k: j.get(k) for k in DIMS}
        got = [v for v in dims.values() if isinstance(v, (int, float))]
        rec = {"序号": r["序号"], "题型": r["题型"], "语言": r.get("语言"),
               "答案字数": r["答案字数"], "引用条数": r["引用条数"],
               "依据类条数": r["依据类条数"], "案例类条数": r["案例类条数"],
               "rerank_top1": r.get("rerank_top1"), "标题重复数": r.get("标题重复数"),
               "题目中的标准号": r.get("题目中的标准号"),
               "引用正文命中的标准号": r.get("引用正文命中的标准号"),
               "引用标题命中的标准号": r.get("引用标题命中的标准号"),
               **dims, "均分": round(sum(got) / len(got), 2) if got else None,
               "fabrications": j.get("fabrications") or [],
               "data_gap": j.get("data_gap"), "answerable": j.get("answerable"),
               "brief": (j.get("brief") or "")[:140], "判分错误": err, "判分耗时s": round(dt, 1)}
        out.append(rec)
        print(f"  [{rec['序号']:>2}] {rec['题型'][:12]:<12} 正确{rec['correctness']} 覆盖{rec['coverage']} "
              f"可操作{rec['actionability']} 有据{rec['grounding']} 边界{rec['boundary']} "
              f"均分{rec['均分']} 编造{len(rec['fabrications'])} gap={rec['data_gap']} "
              f"| {rec['brief'][:44]}", flush=True)
    OUT.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in out), encoding="utf-8")
    if raws:
        RAW.write_text("\n".join(json.dumps(o, ensure_ascii=False) for o in raws), encoding="utf-8")
        print(f"\n⚠️ {len(raws)} 条首轮判分失败 → {RAW.relative_to(WS)}", flush=True)

    sc = [o for o in out if isinstance(o.get("均分"), (int, float))]
    if sc:
        print("\n" + "=" * 104)
        for k in DIMS:
            v = [o[k] for o in sc if isinstance(o.get(k), (int, float))]
            if v:
                print(f"  平均 {k:<14}{sum(v)/len(v):.2f}")
        print(f"  平均总分　　　{sum(o['均分'] for o in sc)/len(sc):.2f}")
        print(f"  有编造指控 {sum(1 for o in sc if o['fabrications'])} 条；"
              f"data_gap=True {sum(1 for o in sc if o['data_gap'])} 条；"
              f"answerable=False {sum(1 for o in sc if o['answerable'] is False)} 条")
    print(f"\n→ {OUT.relative_to(WS)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
