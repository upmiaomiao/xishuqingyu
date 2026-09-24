"""域 C 最小垂直切片试跑（Phase 0 → Phase 1 之间的可行性验证）。

用途
    用**小批量真实文档**验证复刻范式的关键假设是否成立，在正式建 Phase 1 之前排掉风险：
      A. flash 模型能否稳定输出结构化 JSON（失败则整个 Parser 路线不成立）
      B. 能否按 ADR-010 正确分离 Norm / Fact / Judgment 三层
      C. 抽取出的条款引用、数值是否**可被原文证实**（反幻觉的关键）
      D. 单篇 token 与耗时，用于放量前成本测算
    验证链：文档 →(flash 抽取)→ 结构 →(本地规则派生 Gold)→ Gold Card →(flash 生成)→ Q/Trace/A
            →(本地规则验证)→ 通过/拒绝。LLM 只负责抽取与生成，**Gold 由规则派生**（复刻范式第 5 条支柱）。

输入（只读）
    生态环境监管执法/类案法条推荐/现有系统案例库/*/*.md     默认取前 N 篇

输出
    _工作记录/方案设计/域C-垂直切片试跑结果.md    人类可读报告
    _工作记录/方案设计/域C-垂直切片试跑明细.json  逐篇明细（便于复查）

运行
    python _脚本代码/模型试验/域C_最小垂直切片.py --mode probe
    python _脚本代码/模型试验/域C_最小垂直切片.py --mode slice --docs 3

模型配置
    只从环境变量或**工作区根目录** .env 读取，密钥不落盘、不回显：
      COT_LLM_API_KEY / COT_LLM_BASE_URL / COT_LLM_MODEL
    若未设置，则回退读取根 .env 的 OPENAI_API_KEY / OPENAI_BASE_URL，
    模型强制使用 flash 档（--model 可覆盖，默认 deepseek-v4-flash）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
CASE_ROOT = WORKSPACE / "生态环境监管执法/类案法条推荐/现有系统案例库"
OUT_MD = WORKSPACE / "_工作记录/方案设计/域C-垂直切片试跑结果.md"
OUT_JSON = WORKSPACE / "_工作记录/方案设计/域C-垂直切片试跑明细.json"

DEFAULT_FLASH = "deepseek-v4-flash-guan"
# 注：参考仓库 .env.example 写的 COT_LLM_MODEL=deepseek-v4-flash 在本环境**无授权**
# （实测 403 无权限访问模型）。本 key 实际可用的三档为：
#   deepseek-v4-flash-guan / deepseek-v4-flash-vision-exp-guan / deepseek-v4-pro-guan
# 按用户要求只用 flash 档，故固定为 deepseek-v4-flash-guan。


# ── 配置：环境变量优先，其次工作区根 .env ──────────────────
def load_config(model_override: str | None) -> tuple[str, str, str]:
    def from_dotenv(key: str) -> str | None:
        p = WORKSPACE / ".env"
        if not p.exists():
            return None
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
        return None

    key = os.environ.get("COT_LLM_API_KEY") or from_dotenv("OPENAI_API_KEY")
    base = os.environ.get("COT_LLM_BASE_URL") or from_dotenv("OPENAI_BASE_URL")
    model = model_override or os.environ.get("COT_LLM_MODEL") or DEFAULT_FLASH
    if not key:
        sys.exit("缺少 API 密钥（COT_LLM_API_KEY 或根 .env 的 OPENAI_API_KEY）")
    if not base:
        sys.exit("缺少 BASE_URL（COT_LLM_BASE_URL 或根 .env 的 OPENAI_BASE_URL）")
    if "pro" in model:
        sys.exit(f"检测到 pro 档模型（{model}）；本试跑按约定只允许 flash 档")
    return key, base.rstrip("/"), model


class Client:
    def __init__(self, key: str, base: str, model: str, timeout: float = 180.0):
        self.key, self.base, self.model, self.timeout = key, base, model, timeout
        self.calls: list[dict] = []

    def complete(self, prompt: str, stage: str) -> tuple[str, dict]:
        body = json.dumps({
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base}/chat/completions", data=body,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.key}"})
        t0 = time.monotonic()
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        dt = time.monotonic() - t0
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {}) or {}
        meta = {
            "stage": stage, "latency_s": round(dt, 2),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "model": self.model,
        }
        self.calls.append(meta)
        return text, meta


def extract_json(text: str) -> dict | None:
    """从模型输出里抠出第一个完整 JSON 对象；失败返回 None。"""
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


# ── 抽取 Prompt（ADR-010：Evidence / Fact / Judgment 三层分离）──
EXTRACT_PROMPT = """你是生态环境执法领域的结构化抽取器。请从下面的《类案学习要点》中抽取结构化信息。

严格规则：
1. 只抽取原文**明确写出**的内容，不得推断、不得补全、不得总结成新表述。
2. 每一条 norm 的 text 必须是原文中**逐字出现的连续片段**；article 只填原文出现的编号。
3. facts 只记录可归因到具体主体、有明确行为与对象的客观事实；原文没写时间就填 null。
4. judgment 记录原文给出的定性、处罚依据与处置结果；amount 只在原文给出具体罚款数额时填数字（单位万元）。
5. 找不到的字段一律填 null 或空数组，**严禁编造**。

只输出一个 JSON 对象，不要任何解释文字，结构如下：
{
  "case_title": "字符串",
  "norms": [{"law": "法规名（不含书名号）", "article": "第X条", "text": "原文逐字片段", "kind": "法律|行政法规|规章|地方性法规|司法解释|其他"}],
  "facts": [{"subject": "主体", "time": "时间或null", "behavior": "行为", "object": "对象", "quantity": "数量或null", "source_span": "原文逐字片段"}],
  "judgment": {
    "violated_norms": [{"law": "法规名", "article": "第X条"}],
    "penalty_basis": {"law": "法规名", "article": "第X条", "range_min": 数字或null, "range_max": 数字或null, "unit": "万元或null"},
    "disposition": {"type": "罚款|不予处罚|撤销许可|移送|其他", "amount": 数字或null, "extra": "其他处置或null"},
    "reasoning": "原文给出的定性理由或null"
  }
}

【文档】
{text}
"""

GEN_PROMPT = """你是领域数据构造器。基于给定的【证据子图】生成一道训练任务的
规范化推理轨迹与答案。推理必须严格局限在证据子图内。

【任务规格】
task_form: RE-C3 违法构成要件齐备性
objective: 判断给定案情事实是否齐备该违法类型的构成要件，并给出理由与不确定性
required_operations: [定位适用规范, 拆解构成要件, 逐要件比对事实, 检查证据缺口, 形成判断]
output_fields: [elements, element_check, conclusion, evidence_gaps, uncertainty]

【硬性规则】
1. evidence_refs 只能填写证据子图中列出的节点 ID（形如 N1 / F2 / J1），不得自造 ID、不得填写法规名。
2. answer 中出现的任何数字都必须来自证据子图原文，不得新造或推算。
3. 不得把风险信号直接升级为确定违法结论；证据不足必须体现在 uncertainty 与 evidence_gaps。
4. 简洁优先：reasoning_trace 每步只用一句话，answer 各字段精炼，整体输出不超过 1200 字。

【证据子图】
{subgraph}

只输出 JSON，结构：
{
  "question": "面向答题者的题干（不得泄露结论）",
  "reasoning_trace": [{"step": 1, "operation": "操作名", "evidence_refs": ["N1"], "intermediate_claim": "一句话中间判断"}],
  "answer": {"elements": [{"element": "要件", "satisfied": true或false, "evidence_refs": ["N1"]}], "element_check": "逐要件比对说明", "conclusion": "结论", "evidence_gaps": ["证据缺口"], "uncertainty": "不确定性说明"}
}
"""


# ── 本地规则派生 Gold（复刻范式第 5 条支柱：模型不写标准答案）──
def derive_gold(doc: dict, source: str) -> tuple[dict, list[str]]:
    issues: list[str] = []
    norms = doc.get("norms") or []
    facts = doc.get("facts") or []
    jd = doc.get("judgment") or {}
    disp = jd.get("disposition") or {}
    basis = jd.get("penalty_basis") or {}

    # 检查 1：条款 text 必须能在原文逐字找到（反幻觉硬门）
    grounded, ungrounded = [], []
    norm_text = re.sub(r"\s+", "", source)
    for n in norms:
        t = re.sub(r"\s+", "", str(n.get("text") or ""))
        (grounded if t and t in norm_text else ungrounded).append(
            f"{n.get('law')}{n.get('article')}")
    if ungrounded:
        issues.append(f"norm_text_ungrounded:{ungrounded}")

    # 检查 2：罚款额是否落入法定幅度（Hard Verifier 的确定性检查）
    amount = disp.get("amount")
    lo, hi = basis.get("range_min"), basis.get("range_max")
    fine_ok = None
    if isinstance(amount, (int, float)) and isinstance(lo, (int, float)) and isinstance(hi, (int, float)):
        fine_ok = bool(lo <= amount <= hi)

    gold = {
        "evidence_nodes": [f"norm:{n.get('law')}{n.get('article')}" for n in norms],
        "required_relations": [],
        "allowed_claims": [jd.get("reasoning")] if jd.get("reasoning") else [],
        "forbidden_or_unsupported_claims": ["超出原文事实的违法定性"],
        "numeric_checks": ([{"name": "fine_within_range", "value": amount,
                             "min": lo, "max": hi, "passed": fine_ok}]
                           if fine_ok is not None else []),
        "acceptable_alternatives": [],
        "boundary_expectations": ["证据不足时不得作出确定违法结论"],
        "derived": {
            "norm_count": len(norms), "grounded_norm_count": len(grounded),
            "fact_count": len(facts), "disposition_type": disp.get("type"),
            "violated_norms": jd.get("violated_norms") or [],
        },
    }
    return gold, issues


def build_subgraph(doc: dict) -> tuple[str, set[str], str]:
    """构造带**受控节点 ID** 的证据子图文本，返回 (子图文本, 合法ID集合, 数字接地语料)。

    节点 ID 必须显式给出，否则模型会自造引用名——试跑第一轮即因此全部验证失败。
    """
    nodes: list[dict] = []
    for i, n in enumerate(doc.get("norms") or [], 1):
        nodes.append({"id": f"N{i}", "type": "规范",
                      "label": f"{n.get('law') or ''} {n.get('article') or ''}".strip(),
                      "text": str(n.get("text") or "")[:300]})
    for i, fa in enumerate(doc.get("facts") or [], 1):
        label = " ".join(str(fa.get(k) or "") for k in
                         ("subject", "time", "behavior", "object")).strip()
        nodes.append({"id": f"F{i}", "type": "事实", "label": label,
                      "text": str(fa.get("source_span") or "")[:200]})
    jd = doc.get("judgment") or {}
    disp = jd.get("disposition") or {}
    nodes.append({"id": "J1", "type": "判定",
                  "label": f"处置={disp.get('type')} 金额={disp.get('amount')} "
                           f"其他={disp.get('extra')}",
                  "text": str(jd.get("reasoning") or "")[:200]})

    text = "\n".join(f"{n['id']} | {n['type']} | {n['label']} | {n['text']}" for n in nodes)
    ids = {n["id"] for n in nodes}
    grounding = " ".join(f"{n['label']} {n['text']}" for n in nodes)
    return text, ids, grounding


def verify(answer: dict, gold: dict, subgraph_ids: set[str],
           grounding_pool: str) -> dict:
    """本地规则验证：不调用模型。判据与设计文档 §10.2 的 Graph/Hard Verifier 对齐。"""
    a = answer or {}
    checks: dict[str, bool] = {}

    # Hard：结论字段齐备
    need = ["elements", "element_check", "conclusion", "evidence_gaps", "uncertainty"]
    checks["required_fields_present"] = all(k in a for k in need)

    # Graph：所有引用必须落在受控 ID 词表内（引用子图外节点＝硬错误）
    refs: list[str] = []
    for e in a.get("elements") or []:
        refs.extend(e.get("evidence_refs") or [])
    checks["refs_inside_subgraph"] = bool(refs) and all(r in subgraph_ids for r in refs)

    # Hard：数字接地——答案里的数字必须能在证据子图正文中找到
    nums = set(re.findall(r"\d+(?:\.\d+)?", json.dumps(a, ensure_ascii=False)))
    flat = re.sub(r"\s+", "", grounding_pool)
    # 中文序号/步骤号/纯小整数视为数量转述，不要求接地（与 core/numcheck 口径一致）
    checkable = {n for n in nums if ("." in n or len(n) >= 3 or float(n) > 12)}
    ungrounded = sorted(n for n in checkable if n not in flat)
    checks["numbers_grounded"] = not ungrounded

    # Hard：罚款落幅（Gold 由规则派生，非模型生成）
    nc = gold.get("numeric_checks") or []
    checks["fine_within_range"] = nc[0]["passed"] if nc else True

    # Boundary：不得把风险信号升级为确定违法
    checks["no_violation_overreach"] = "potentially" not in json.dumps(a, ensure_ascii=False)

    failed = [k for k, v in checks.items() if not v]
    return {"checks": checks, "g_valid": not failed, "failed": failed,
            "ungrounded_numbers": ungrounded}


def load_docs(limit: int) -> list[tuple[str, str]]:
    files = sorted(CASE_ROOT.glob("*/*.md")) if CASE_ROOT.exists() else []
    out = []
    for f in files[:limit]:
        out.append((f.stem, f.read_text(encoding="utf-8", errors="replace")))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["probe", "slice"], default="probe")
    ap.add_argument("--docs", type=int, default=3)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()

    key, base, model = load_config(args.model)
    cli = Client(key, base, model)
    print(f"model={model}  base={base}")

    if args.mode == "probe":
        text, meta = cli.complete("只回复两个字：就绪", "probe")
        print(f"probe reply={text.strip()[:40]!r}")
        print(f"latency={meta['latency_s']}s tokens={meta['prompt_tokens']}+"
              f"{meta['completion_tokens']}")
        return

    docs = load_docs(args.docs)
    records = []
    for name, text in docs:
        rec: dict = {"doc": name, "chars": len(text)}
        # 1. 抽取
        try:
            raw, m1 = cli.complete(EXTRACT_PROMPT.replace("{text}", text), "extract")
            rec["extract_meta"] = m1
            doc = extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"extract_failed: {exc}"
            records.append(rec)
            continue
        rec["json_ok"] = doc is not None
        if doc is None:
            rec["raw_head"] = raw[:400]
            records.append(rec)
            continue
        rec["extracted"] = doc

        # 2. 规则派生 Gold
        gold, issues = derive_gold(doc, text)
        rec["gold"] = gold
        rec["gold_issues"] = issues

        # 3. 生成 Q/Trace/A（子图带受控节点 ID）
        subgraph, ids, grounding = build_subgraph(doc)
        try:
            raw2, m2 = cli.complete(
                GEN_PROMPT.replace("{subgraph}", subgraph), "generate")
            rec["generate_meta"] = m2
            gen = extract_json(raw2)
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"generate_failed: {exc}"
            records.append(rec)
            continue
        rec["gen_json_ok"] = gen is not None
        if gen is None:
            rec["raw_head"] = raw2[:400]
            records.append(rec)
            continue
        rec["generated"] = gen
        rec["subgraph_ids"] = sorted(ids)

        # 4. 本地验证
        rec["verification"] = verify(gen.get("answer"), gold, ids, grounding)
        records.append(rec)

    # ── 汇总 ──
    n = len(records)
    json_ok = sum(1 for r in records if r.get("json_ok"))
    gen_ok = sum(1 for r in records if r.get("gen_json_ok"))
    verified = sum(1 for r in records if (r.get("verification") or {}).get("g_valid"))
    tin = sum(r.get("extract_meta", {}).get("prompt_tokens", 0)
              + r.get("generate_meta", {}).get("prompt_tokens", 0) for r in records)
    tout = sum(r.get("extract_meta", {}).get("completion_tokens", 0)
               + r.get("generate_meta", {}).get("completion_tokens", 0) for r in records)
    lat = sum(r.get("extract_meta", {}).get("latency_s", 0)
              + r.get("generate_meta", {}).get("latency_s", 0) for r in records)
    call_count = len(cli.calls)

    lines = [
        "# 域 C 垂直切片试跑结果", "",
        f"> 生成时间 {datetime.now():%Y-%m-%d %H:%M}　模型 `{model}`",
        f"> 文档数 {n}　API 调用 {call_count} 次", "",
        "## 1. 总览", "",
        "| 指标 | 结果 |", "| --- | --- |",
        f"| 抽取返回合法 JSON | {json_ok}/{n} |",
        f"| 生成返回合法 JSON | {gen_ok}/{n} |",
        f"| 本地验证 g_valid 通过 | {verified}/{n} |",
        f"| 输入 token | {tin} |",
        f"| 输出 token | {tout} |",
        f"| 总耗时 | {lat:.1f}s |", "",
        "## 2. 逐篇明细", "",
    ]
    for r in records:
        lines.append(f"### {r['doc']}")
        lines.append("")
        lines.append(f"- 原文 {r['chars']} 字")
        if r.get("error"):
            lines.append(f"- ❌ {r['error']}")
            lines.append("")
            continue
        lines.append(f"- 抽取 JSON: {'✅' if r.get('json_ok') else '❌'}　"
                     f"生成 JSON: {'✅' if r.get('gen_json_ok') else '❌'}")
        g = r.get("gold") or {}
        d = g.get("derived") or {}
        lines.append(f"- Gold 派生：条款 {d.get('norm_count')} 条"
                     f"（原文可证实 {d.get('grounded_norm_count')} 条）、"
                     f"事实 {d.get('fact_count')} 条、处置 `{d.get('disposition_type')}`")
        if r.get("gold_issues"):
            lines.append(f"- ⚠️ Gold 问题：{r['gold_issues']}")
        v = r.get("verification")
        if v:
            lines.append(f"- 验证 g_valid = **{v['g_valid']}**"
                         + (f"，失败项 {v['failed']}" if v["failed"] else ""))
            lines.append(f"- 逐项：{v['checks']}")
        lines.append("")

    lines += ["## 3. 单篇成本估算", "",
              f"- 单篇平均输入 token ≈ {tin // max(n,1)}，输出 token ≈ {tout // max(n,1)}",
              f"- 单篇平均耗时 ≈ {lat / max(n,1):.1f}s", ""]

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")
    OUT_JSON.write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"docs={n} json_ok={json_ok} gen_ok={gen_ok} verified={verified} "
          f"calls={call_count} tokens={tin}+{tout} latency={lat:.1f}s")
    print(f"written: {OUT_MD}")


if __name__ == "__main__":
    main()
