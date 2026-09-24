"""域 C 可见性配置 × 负样本构造 对照试验。

背景
    首轮小批量试跑（域C_最小垂直切片.py）暴露两个问题：
      问题1 全 ✅ 偏置：13/13 个要件全部判「满足」，模型从不判「不满足」
      问题2 题干泄漏：题干直接给出条款号与要件措辞（违反设计文档 §9.3）
    用户已裁定问题1 采用方案 A：**加负样本构造**。
    本试验同时对照三种可见性配置，用数据判断「不给条款号/不给要件措辞」能否消除泄漏，
    以及负样本能否让模型产出「不满足」判断。

三种可见性配置（对应设计文档 §9.3 Evidence 可见性）
    V1_现行      题干给条款号 + 要件措辞（复现泄漏基线）
    V2_仅事实    题干只给事实，不给法规、不给要件
    V3_候选条文  题干给事实 + 候选条文原文（不标条款号、不标哪条适用、含 2 条干扰）

负样本构造（方案 A）
    正例跑完后，**机械删掉支撑某要件的最后一条事实节点**，同 prompt 再跑一次。
    若模型仍判「齐备」，说明它没有做真正的事实比对 —— 这是判别力的直接度量。

输入（只读）
    生态环境监管执法/类案法条推荐/现有系统案例库/*/*.md

输出
    _工作记录/方案设计/域C-可见性与负样本试验.md
    _工作记录/方案设计/域C-可见性与负样本明细.json

运行
    python _脚本代码/模型试验/域C_可见性与负样本试验.py --docs 3

模型
    固定 flash 档 deepseek-v4-flash-guan；密钥只从环境变量或根 .env 读取，不落盘。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
CASE_ROOT = WORKSPACE / "生态环境监管执法/类案法条推荐/现有系统案例库"
OUT_MD = WORKSPACE / "_工作记录/方案设计/域C-可见性与负样本试验.md"
OUT_JSON = WORKSPACE / "_工作记录/方案设计/域C-可见性与负样本明细.json"
DEFAULT_FLASH = "deepseek-v4-flash-guan"

ARTICLE_RE = re.compile(r"第[一二三四五六七八九十百零〇\d]+条")


# ── 配置 ──────────────────────────────────────────────────
def load_config(model_override: str | None) -> tuple[str, str, str]:
    def from_dotenv(key: str) -> str | None:
        p = WORKSPACE / ".env"
        if not p.exists():
            return None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip().strip('"').strip("'")
        return None

    key = os.environ.get("COT_LLM_API_KEY") or from_dotenv("OPENAI_API_KEY")
    base = os.environ.get("COT_LLM_BASE_URL") or from_dotenv("OPENAI_BASE_URL")
    model = model_override or os.environ.get("COT_LLM_MODEL") or DEFAULT_FLASH
    if not key:
        sys.exit("缺少 API 密钥")
    if not base:
        sys.exit("缺少 BASE_URL")
    if "pro" in model:
        sys.exit(f"按约定只用 flash 档，拒绝 pro：{model}")
    return key, base.rstrip("/"), model


class Client:
    def __init__(self, key: str, base: str, model: str, timeout: float = 300.0):
        self.key, self.base, self.model, self.timeout = key, base, model, timeout
        self.calls: list[dict] = []

    def complete(self, prompt: str, stage: str) -> tuple[str, dict]:
        body = json.dumps({"model": self.model,
                           "messages": [{"role": "user", "content": prompt}],
                           "temperature": 0.0}).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        dt = time.monotonic() - t0
        usage = data.get("usage", {}) or {}
        meta = {"stage": stage, "latency_s": round(dt, 2),
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0)}
        self.calls.append(meta)
        return data["choices"][0]["message"]["content"], meta


def extract_json(text: str) -> dict | None:
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    raw = fence.group(1) if fence else text
    start = raw.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(raw)):
        if raw[i] == "{":
            depth += 1
        elif raw[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(raw[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


EXTRACT_PROMPT = """你是生态环境执法领域的结构化抽取器。请从下面的《类案学习要点》中抽取结构化信息。

严格规则：
1. 只抽取原文**明确写出**的内容，不得推断、不得补全、不得总结成新表述。
2. 每一条 norm 的 text 必须是原文中**逐字出现的连续片段**；article 只填原文出现的编号。
3. facts 只记录可归因到具体主体、有明确行为与对象的客观事实；原文没写时间就填 null。
4. judgment 记录原文给出的定性、处罚依据与处置结果；amount 只在原文给出具体罚款数额时填数字（万元）。
5. 找不到的字段一律填 null 或空数组，**严禁编造**。

只输出一个 JSON 对象，不要任何解释文字，结构如下：
{
  "case_title": "字符串",
  "norms": [{"law": "法规名（不含书名号）", "article": "第X条", "text": "原文逐字片段", "kind": "法律|行政法规|规章|地方性法规|司法解释|其他"}],
  "facts": [{"subject": "主体", "time": "时间或null", "behavior": "行为", "object": "对象", "quantity": "数量或null", "source_span": "原文逐字片段"}],
  "judgment": {"violated_norms": [{"law": "法规名", "article": "第X条"}],
    "penalty_basis": {"law": "法规名", "article": "第X条", "range_min": 数字或null, "range_max": 数字或null, "unit": "万元或null"},
    "disposition": {"type": "罚款|不予处罚|撤销许可|移送|其他", "amount": 数字或null, "extra": "其他处置或null"},
    "reasoning": "原文给出的定性理由或null"}
}

【文档】
{text}
"""

# ── 三种可见性配置的生成 prompt ─────────────────────────────
_COMMON_TAIL = """
【硬性规则】
1. evidence_refs 只能填写证据子图中列出的节点 ID（形如 N1 / F2），不得自造。
2. answer 中出现的任何数字都必须来自证据子图原文。
3. 不得把风险信号直接升级为确定违法结论；证据不足必须体现在 uncertainty 与 evidence_gaps。
4. reasoning_trace 每步一句话，整体输出不超过 1200 字。

只输出 JSON：
{"question": "题干", "reasoning_trace": [{"step": 1, "operation": "操作名", "evidence_refs": ["F1"], "intermediate_claim": "一句话"}],
 "answer": {"elements": [{"element": "要件", "satisfied": true, "evidence_refs": ["F1"]}], "element_check": "逐要件比对说明", "conclusion": "结论", "evidence_gaps": ["缺口"], "uncertainty": "说明"}}
"""

PROMPT_V1 = """你是领域数据构造器。以下是**已定案**的案件，请据此生成一道训练任务。

【任务规格】task_form: RE-C3 违法构成要件齐备性
objective: 判断事实是否齐备该违法类型的构成要件

【证据子图】
{subgraph}

【可引用法规】（题库已知的适用规范，题干中可写出其名称与条款号）
{norms}

""" + _COMMON_TAIL

PROMPT_V2 = """你是领域数据构造器。以下是**已定案**的案件，请据此生成一道训练任务。

【任务规格】task_form: RE-C1+C3 规范定位与要件齐备性
objective: 仅依据事实，自行判断应适用何种规范，并判断是否齐备该规范的违法构成要件

【证据子图】（**只给事实，不给任何法规**）
{subgraph}

【题干硬性约束】
- 题干**只能描述事实与任务**，不得出现任何法规名称、条款编号，不得出现构成要件的措辞。
- 答题者必须自己从领域知识判断适用规范与构成要件。

""" + _COMMON_TAIL

PROMPT_V3 = """你是领域数据构造器。以下是**已定案**的案件，请据此生成一道训练任务。

【任务规格】task_form: RE-C3 违法构成要件齐备性
objective: 从下列候选条文中自行确定适用条文，拆解其构成要件，并逐要件比对事实

【证据子图】（事实）
{subgraph}

【候选条文】（**未标注条款号，也未标注哪一条适用**，其中含干扰项）
{candidates}

【题干硬性约束】
- 题干**不得写出任何条款编号**，也不得复述构成要件的措辞。
- 答题者需自行判断哪条适用、并自行拆解要件。

""" + _COMMON_TAIL


# ── 子图构造 ───────────────────────────────────────────────
def build_nodes(doc: dict, drop_last_fact: bool = False) -> list[dict]:
    nodes: list[dict] = []
    for i, n in enumerate(doc.get("norms") or [], 1):
        nodes.append({"id": f"N{i}", "type": "规范",
                      "label": f"{n.get('law') or ''} {n.get('article') or ''}".strip(),
                      "text": str(n.get("text") or "")[:300]})
    facts = list(doc.get("facts") or [])
    if drop_last_fact and len(facts) > 1:
        facts = facts[:-1]          # 负样本：机械删掉最后一条事实
    for i, fa in enumerate(facts, 1):
        label = " ".join(str(fa.get(k) or "") for k in
                         ("subject", "time", "behavior", "object")).strip()
        nodes.append({"id": f"F{i}", "type": "事实", "label": label,
                      "text": str(fa.get("source_span") or "")[:200]})
    return nodes


def render(nodes: list[dict]) -> str:
    return "\n".join(f"{n['id']} | {n['type']} | {n['label']} | {n['text']}" for n in nodes)


def pick_distractors(all_norms: list[str], correct: list[str], k: int = 2) -> list[str]:
    pool = [n for n in all_norms if n not in correct]
    return pool[:k]


# ── 指标 ───────────────────────────────────────────────────
def leakage_metrics(question: str, doc: dict) -> dict:
    gold_articles = {n.get("article") for n in (doc.get("norms") or []) if n.get("article")}
    gold_laws = {n.get("law") for n in (doc.get("norms") or []) if n.get("law")}
    q_articles = set(ARTICLE_RE.findall(question))
    return {
        "q_len": len(question),
        "leak_article": bool(q_articles & gold_articles),
        "leak_law": any(l and l in question for l in gold_laws),
        "leaked_articles": sorted(q_articles & gold_articles),
    }


def satisfaction(answer: dict) -> tuple[int, int]:
    els = (answer or {}).get("elements") or []
    total = len(els)
    sat = sum(1 for e in els if e.get("satisfied") is True)
    return sat, total


def verify(answer: dict, ids: set[str], grounding: str) -> dict:
    a = answer or {}
    checks: dict[str, bool] = {}
    need = ["elements", "element_check", "conclusion", "evidence_gaps", "uncertainty"]
    checks["required_fields_present"] = all(k in a for k in need)
    refs: list[str] = []
    for e in a.get("elements") or []:
        refs.extend(e.get("evidence_refs") or [])
    checks["refs_inside_subgraph"] = bool(refs) and all(r in ids for r in refs)
    nums = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(a, ensure_ascii=False)))
    flat = re.sub(r"\s+", "", grounding)
    checkable = {n for n in nums if ("." in n or len(n) >= 3 or float(n) > 12)}
    ungrounded = sorted(n for n in checkable if n not in flat)
    checks["numbers_grounded"] = not ungrounded
    failed = [k for k, v in checks.items() if not v]
    return {"checks": checks, "g_valid": not failed, "failed": failed,
            "ungrounded_numbers": ungrounded}


def run_one(cli: Client, prompt: str, stage: str) -> tuple[dict | None, dict, str]:
    raw, meta = cli.complete(prompt, stage)
    parsed = extract_json(raw)
    print(f"  [{stage}] {meta['latency_s']}s "
          f"{meta['prompt_tokens']}+{meta['completion_tokens']}tok "
          f"json={'ok' if parsed else 'FAIL'}", flush=True)
    return parsed, meta, raw


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    key, base, model = load_config(args.model)
    cli = Client(key, base, model)
    print(f"model={model}")

    files = sorted(CASE_ROOT.glob("*/*.md"))[:args.docs]
    # 干扰条文池：从其它文档的法规名里取
    records: list[dict] = []

    # 先抽取全部文档（三种配置共用抽取结果）
    extracted: list[tuple[str, str, dict]] = []
    for f in files:
        text = f.read_text(encoding="utf-8", errors="replace")
        doc, meta, _ = run_one(cli, EXTRACT_PROMPT.replace("{text}", text), "extract")
        extracted.append((f.stem, text, doc or {}))
    all_laws = sorted({n.get("law") for _, _, d in extracted
                       for n in (d.get("norms") or []) if n.get("law")})

    # 全库条文池：用于给 V3 挑干扰条文（取自其它文档）
    norm_pool: list[tuple[str, str, str]] = []
    for _n, _t, _d in extracted:
        for x in (_d.get("norms") or []):
            if x.get("law") and x.get("text"):
                norm_pool.append((str(x["law"]), str(x.get("article") or ""),
                                  str(x["text"])))

    for name, text, doc in extracted:
        rec: dict = {"doc": name, "chars": len(text)}
        if not doc:
            rec["error"] = "extract_failed"
            records.append(rec)
            continue
        norms = doc.get("norms") or []
        own_laws = {str(n.get("law")) for n in norms if n.get("law")}
        # 干扰条文：取自其它文档、且法规名不在本文档内
        distractors = [p for p in norm_pool if p[0] not in own_laws][:2]
        # V3 候选条文：本文档全部条文 + 干扰条文；**剥掉条款号**，按固定顺序打乱
        cand_lines: list[str] = []
        for i, x in enumerate(norms[:3]):
            body = ARTICLE_RE.sub("", str(x.get("text") or ""))[:200]
            cand_lines.append(f"候选{chr(65+i)} | {x.get('law')} | {body}")
        base = len(cand_lines)
        for j, (lw, _art, body) in enumerate(distractors):
            cand_lines.append(
                f"候选{chr(65+base+j)} | {lw} | {ARTICLE_RE.sub('', body)[:200]}")
        candidate_text = "\n".join(cand_lines)

        rec["norms_count"] = len(norms)
        rec["candidates"] = [c.split(" | ")[1] for c in cand_lines]
        modes = {}

        for mode in ("V1_现行", "V2_仅事实", "V3_候选条文"):
            drop = False
            nodes = build_nodes(doc, drop_last_fact=drop)
            sub, ids = render(nodes), {n["id"] for n in nodes}
            grounding = " ".join(f"{n['label']} {n['text']}" for n in nodes)
            if mode == "V1_现行":
                prompt = PROMPT_V1.replace("{subgraph}", sub).replace(
                    "{norms}", "\n".join(f"{n.get('law')} {n.get('article')}" for n in norms))
            elif mode == "V2_仅事实":
                facts_only = [n for n in nodes if n["type"] == "事实"]
                sub = render(facts_only)
                ids = {n["id"] for n in facts_only}
                grounding = " ".join(f"{n['label']} {n['text']}" for n in facts_only)
                prompt = PROMPT_V2.replace("{subgraph}", sub)
            else:
                prompt = PROMPT_V3.replace("{subgraph}", sub).replace(
                    "{candidates}", candidate_text)
            gen, meta, raw = run_one(cli, prompt, f"{mode}:generate")
            if gen is None:
                modes[mode] = {"error": "gen_json_failed", "raw_head": raw[:200]}
                continue
            ans = gen.get("answer") or {}
            sat, tot = satisfaction(ans)
            modes[mode] = {
                "question": gen.get("question", ""),
                "leakage": leakage_metrics(gen.get("question", ""), doc),
                "satisfied": sat, "elements_total": tot,
                "conclusion": str(ans.get("conclusion", ""))[:200],
                "verification": verify(ans, ids, grounding),
                "meta": meta,
            }
        rec["modes"] = modes

        # 负样本（方案 A）：仅对 V2 跑，机械删一条事实
        nodes = build_nodes(doc, drop_last_fact=True)
        facts_only = [n for n in nodes if n["type"] == "事实"]
        if len(facts_only) >= 1 and len(doc.get("facts") or []) > 1:
            sub = render(facts_only)
            ids = {n["id"] for n in facts_only}
            grounding = " ".join(f"{n['label']} {n['text']}" for n in facts_only)
            gen, meta, raw = run_one(
                cli, PROMPT_V2.replace("{subgraph}", sub), "NEG:generate")
            if gen:
                ans = gen.get("answer") or {}
                sat, tot = satisfaction(ans)
                rec["negative"] = {
                    "dropped_facts": len(doc.get("facts") or []) - len(facts_only),
                    "satisfied": sat, "elements_total": tot,
                    "conclusion": str(ans.get("conclusion", ""))[:200],
                    "verification": verify(ans, ids, grounding),
                }
            else:
                rec["negative"] = {"error": "gen_json_failed"}
        records.append(rec)

    # ── 汇总 ──
    mode_names = ["V1_现行", "V2_仅事实", "V3_候选条文"]
    lines = [
        "# 域 C 可见性配置 × 负样本构造 对照试验", "",
        f"> 生成时间 {datetime.now():%Y-%m-%d %H:%M}　模型 `{model}`",
        f"> 文档数 {len(records)}　API 调用 {len(cli.calls)} 次", "",
        "## 1. 三种可见性配置对照", "",
        "| 指标 | V1 现行(给条款号+要件) | V2 仅事实 | V3 候选条文 |",
        "| --- | --- | --- | --- |",
    ]

    def agg(key: str, mode: str):
        vals = [r["modes"][mode] for r in records
                if r.get("modes", {}).get(mode) and "error" not in r["modes"][mode]]
        return vals

    for label, fn in [
        ("题干泄露条款号比例", lambda v: f"{sum(1 for x in v if x['leakage']['leak_article'])}/{len(v)}"),
        ("题干泄露法规名比例", lambda v: f"{sum(1 for x in v if x['leakage']['leak_law'])}/{len(v)}"),
        ("要件判「满足」比例", lambda v: f"{sum(x['satisfied'] for x in v)}/{sum(x['elements_total'] for x in v)}"),
        ("g_valid 通过", lambda v: f"{sum(1 for x in v if x['verification']['g_valid'])}/{len(v)}"),
        ("平均题干长度", lambda v: f"{sum(x['leakage']['q_len'] for x in v)//max(len(v),1)} 字"),
    ]:
        cells = []
        for m in mode_names:
            v = agg("x", m)
            cells.append(fn(v) if v else "—")
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    lines.append("")

    neg = [r["negative"] for r in records if r.get("negative") and "error" not in r["negative"]]
    lines += ["## 2. 负样本构造效果（V2 配置，删掉一条事实后重跑）", ""]
    if neg:
        pos_sat = sum(r["modes"]["V2_仅事实"]["satisfied"] for r in records
                      if r.get("modes", {}).get("V2_仅事实"))
        pos_tot = sum(r["modes"]["V2_仅事实"]["elements_total"] for r in records
                      if r.get("modes", {}).get("V2_仅事实"))
        neg_sat = sum(x["satisfied"] for x in neg)
        neg_tot = sum(x["elements_total"] for x in neg)
        lines += ["| 条件 | 要件判「满足」比例 |", "| --- | --- |",
                  f"| 正例（原始事实） | {pos_sat}/{pos_tot} |",
                  f"| 负例（删一条事实） | {neg_sat}/{neg_tot} |", ""]
    else:
        lines.append("（无有效负样本）")
        lines.append("")

    lines += ["## 3. 逐篇明细", ""]
    for r in records:
        lines.append(f"### {r['doc'][:70]}")
        lines.append("")
        if r.get("error"):
            lines.append(f"- ❌ {r['error']}")
            lines.append("")
            continue
        lines.append(f"- 原文 {r['chars']} 字，抽取条款 {r['norms_count']} 条")
        for m in mode_names:
            x = (r.get("modes") or {}).get(m)
            if not x:
                continue
            if "error" in x:
                lines.append(f"- **{m}**：❌ {x['error']}")
                continue
            lk = x["leakage"]
            lines.append(
                f"- **{m}**：泄漏条款号={lk['leak_article']}{lk['leaked_articles'] or ''}，"
                f"泄漏法规名={lk['leak_law']}，要件满足 {x['satisfied']}/{x['elements_total']}，"
                f"g_valid={x['verification']['g_valid']}")
        if r.get("negative") and "error" not in r["negative"]:
            n = r["negative"]
            lines.append(f"- **负例(删{n['dropped_facts']}条事实)**："
                         f"要件满足 {n['satisfied']}/{n['elements_total']}")
        lines.append("")
        for m in mode_names:
            x = (r.get("modes") or {}).get(m)
            if x and x.get("question"):
                lines.append(f"  - {m} 题干：{x['question'][:160]}")
        lines.append("")

    tt = sum(c["prompt_tokens"] for c in cli.calls)
    to = sum(c["completion_tokens"] for c in cli.calls)
    lines += ["## 4. 成本", "",
              f"- 调用 {len(cli.calls)} 次，输入 {tt} token，输出 {to} token", ""]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"calls={len(cli.calls)} tokens={tt}+{to}")
    print(f"written: {OUT_MD}")


if __name__ == "__main__":
    main()
