"""域 C 数据集质量分析（只读导出产物，不调用模型）。

用途
    质量门（`registry.evaluate_gate`）只回答"能否注册为可生产 Form"，
    回答不了"这批数据的**质量画像**如何"。本脚本补上后者：

    1. 规模与分层构成
    2. 逐实例的信号强度：要件数、满足率、引用密度
    3. 奖励分布：**暴露 r_soft 饱和**（对 RL 无梯度）
    4. 负例质量：突变类型、反转规则、判别力
    5. 偏好对质量：降级类型分布、reward 落差
    6. 泄漏与污染检查（条款号、题干复述、重复样本）
    7. 覆盖度：案件 / 条文 / 事实节点

用法
    python _脚本代码/质量校验/域C数据集质量分析.py <exports/<run_id>>
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0}
    s = sorted(values)
    return {"n": len(s), "min": round(s[0], 4), "p25": round(s[len(s) // 4], 4),
            "median": round(s[len(s) // 2], 4), "p75": round(s[3 * len(s) // 4], 4),
            "max": round(s[-1], 4), "mean": round(sum(s) / len(s), 4)}


def analyse(root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    natural = load_jsonl(root / "natural" / "instances.jsonl")
    synthetic = load_jsonl(root / "synthetic" / "instances.jsonl")
    pairs = load_jsonl(root / "pairs" / "preference.jsonl")
    inst = natural + synthetic
    pos = [i for i in inst if i["kind"] == "positive"]
    neg = [i for i in inst if i["kind"] == "negative"]

    out: dict = {"run_id": manifest.get("run_id"), "root": str(root)}

    # ── 1. 规模与构成 ──
    out["scale"] = {
        "instances": len(inst), "positive": len(pos), "negative": len(neg),
        "natural": len(natural), "synthetic": len(synthetic),
        "synthetic_share": manifest["composition"]["synthetic_share"],
        "preference_pairs": len(pairs),
        "cases": len({i["case_id"] for i in inst}),
        "splits": manifest["splits"],
    }

    # ── 2. 逐实例信号强度 ──
    def elements(i):
        return (i.get("answer") or {}).get("elements") or []

    out["signal"] = {
        "elements_per_instance": _stats([len(elements(i)) for i in inst]),
        "positive_satisfied_rate": _stats(
            [sum(1 for e in elements(i) if e["satisfied"]) / max(len(elements(i)), 1)
             for i in pos]),
        "negative_satisfied_rate": _stats(
            [sum(1 for e in elements(i) if e["satisfied"]) / max(len(elements(i)), 1)
             for i in neg]),
        "evidence_refs_per_satisfied_element": _stats(
            [len(e["evidence_refs"]) for i in inst for e in elements(i)
             if e["satisfied"]]),
        # 正例里一个「不满足」要件都没有 = 该实例教不了「何时不算违法」
        "positives_with_zero_unsatisfied": sum(
            1 for i in pos if all(e["satisfied"] for e in elements(i))),
        # 负例里全是「满足」= 突变没生效或模型没识别，判别失败
        "negatives_with_zero_unsatisfied": sum(
            1 for i in neg if all(e["satisfied"] for e in elements(i))),
    }

    # ── 3. 奖励分布（暴露饱和）──
    def comp(i, name):
        return ((i.get("verification") or {}).get("components") or {}).get(name)

    out["reward"] = {
        "r_soft": _stats([(i["verification"] or {}).get("r_soft", 0) for i in inst]),
        "r_total": _stats([(i["verification"] or {}).get("r_total", 0) for i in inst]),
        "R_answer": _stats([comp(i, "R_answer") for i in inst]),
        "R_evidence": _stats([comp(i, "R_evidence") for i in inst]),
        "R_reasoning": _stats([comp(i, "R_reasoning") for i in inst]),
        "R_boundary": _stats([comp(i, "R_boundary") for i in inst]),
        "r_soft_saturated_at_1": sum(
            1 for i in inst if (i["verification"] or {}).get("r_soft") == 1.0),
        "g_valid_zero": sum(
            1 for i in inst if (i["verification"] or {}).get("g_valid") == 0.0),
    }

    # ── 4. 负例质量 ──
    out["negative_quality"] = {
        "mutation_types": dict(Counter(
            (i.get("mutation") or {}).get("mutation_type") for i in neg)),
        "flip_rules": dict(Counter(
            ((i.get("mutation") or {}).get("flip_rule") or "").split(":")[-1]
            for i in neg if (i.get("mutation") or {}).get("flip_rule"))),
        "discriminative": sum(
            1 for i in neg if (i["verification"] or {}).get("discriminative")),
        "changed_facts_dist": dict(Counter(
            len((i.get("mutation") or {}).get("changed_facts") or []) for i in neg)),
        "low_confidence": sum(
            1 for i in neg if (i.get("mutation") or {}).get("low_confidence")),
        "mutations_touching_multiple_facts": sum(
            1 for i in neg
            if len((i.get("mutation") or {}).get("changed_facts") or []) > 1),
    }

    # ── 5. 偏好对质量 ──
    out["pair_quality"] = {
        "kinds": dict(Counter(
            (p["rejected"].get("degradation") or {}).get("kind") for p in pairs)),
        "expected_failures": dict(Counter(
            (p["rejected"].get("degradation") or {}).get("expected_failure")
            for p in pairs)),
        "reward_gap": _stats([p.get("reward_gap", 0) for p in pairs]),
        "pairs_with_zero_gap": sum(1 for p in pairs if not p.get("reward_gap")),
        "chosen_g_valid_zero": sum(
            1 for p in pairs if (p["chosen"].get("verification") or {}).get("g_valid") == 0),
    }

    # ── 6. 泄漏与污染 ──
    # 注意：负例**故意复用**正例题干（OPEN-4 = b），所以"题干重复"本身不是缺陷。
    # 真正的问题是：同一题干跨案件复用，或同一题干下出现多个正例。
    qs = [i.get("question") or "" for i in inst]
    spans = [json.dumps(i.get("visible_evidence") or {}, ensure_ascii=False) for i in inst]
    by_q: dict[str, list[dict]] = {}
    for i in inst:
        by_q.setdefault(i.get("question") or "", []).append(i)
    cross_case_dup = sum(1 for g in by_q.values()
                         if len({i["case_id"] for i in g}) > 1)
    multi_positive = sum(1 for g in by_q.values()
                         if sum(1 for i in g if i["kind"] == "positive") > 1)
    neg_reusing = sum(1 for i in inst
                      if i["kind"] == "negative"
                      and (i.get("question_shared_with_positive")
                           or (i.get("verification") or {}).get("kind") == "negative"))
    out["leakage"] = {
        "article_leak": sum(1 for i in inst
                            if (i.get("leakage") or {}).get("leak_article")),
        "law_name_in_question": sum(
            1 for i in inst
            if (i["verification"].get("observed") or {}).get("law_names_in_question")),
        "fact_restatement": sum(
            1 for i in inst if "no_fact_restatement" in
            ((i["verification"].get("checks") or {}).get("hard") or {})
            and not i["verification"]["checks"]["hard"]["no_fact_restatement"]),
        # 这些才是真问题
        "question_shared_across_cases": cross_case_dup,
        "multiple_positives_same_question": multi_positive,
        "duplicate_visible_evidence": len(spans) - len(set(spans)),
        "duplicate_instance_ids": len(inst) - len({i["instance_id"] for i in inst}),
        # 这个是设计使然，仅作信息
        "negatives_reusing_positive_question": neg_reusing,
        "distinct_questions": len(set(qs)),
    }

    # ── 7. 覆盖度 ──
    norms_per = [(i.get("visible_evidence") or {}).get("candidate_map") or {} for i in inst]
    out["coverage"] = {
        "distinct_candidate_norms": len({v for m in norms_per for v in m.values()}),
        "distinct_visible_nodes": len({n for i in inst
                                       for n in (i.get("visible_ids") or [])}),
        "cases_with_positive": len({i["case_id"] for i in pos}),
        "cases_with_negative": len({i["case_id"] for i in neg}),
        "cases_with_pair": len({p["case_id"] for p in pairs}),
    }

    # ── 8. 长度 ──
    out["lengths"] = {
        "question_chars": _stats([len(i.get("question") or "") for i in inst]),
        "answer_rendered_chars": _stats(
            [len((i.get("answer") or {}).get("conclusion") or "") for i in inst]),
        "context_chars": _stats(
            [len((i.get("visible_evidence") or {}).get("facts") or "")
             + len((i.get("visible_evidence") or {}).get("candidates") or "")
             for i in inst]),
    }

    # ── 9. SFT 样本专有检查 ──
    out["sft"] = analyse_sft(root)
    return out


_BAD_TAIL = ("：", ":", "、", "，", ",")


def _parse_blocks(text: str) -> list[tuple[str, str, str]]:
    """解析 `标签 | 法规 | 正文` 候选块，**把续行并入上一条正文**。

    为什么必须这么写：源文本的枚举项带换行（`\\n\\n（一）…`），正文里的换行会
    让「按行切分」的解析只读到第一行 —— 我早期的度量脚本就因此量出错误的正文长度，
    进而把一个截断缺陷误判成别的原因。域 C v6 起正文已折叠换行，但本函数
    对历史产物（v3~v5）仍要正确，故保留续行合并逻辑。
    """
    import re
    out: list[tuple[str, str, str]] = []
    cur: list[str] | None = None
    for ln in (text or "").split("\n"):
        if re.match(r"^候选\S*\s*\|", ln):
            if cur:
                out.append(tuple(cur))  # type: ignore[arg-type]
            p = ln.split("|", 2)
            cur = [p[0].strip(), p[1].strip(), p[2] if len(p) > 2 else ""]
        elif cur:
            cur[2] += "\n" + ln
    if cur:
        out.append(tuple(cur))  # type: ignore[arg-type]
    return out


def analyse_sft(root: Path) -> dict:
    """SFT 样本专有质量检查。

    SFT 与 RL 的质量关注点不同：SFT 只看 prompt/completion 这对文本本身，
    因此要单独查三件在实例层面查不出来的事：
      1. **completion 是否出现条款号** —— 候选条文已匿名化，模型无从知道条款号，
         若 completion 写了条款号，等于教模型编造它不可能知道的信息。
      2. **干扰项是否够格** —— 干扰项若与案情明显无关（甚至与 gold 同法），
         "找适用条文"这一步会退化成近乎白给。
      3. **候选条文是否残句** —— 抽取出的条文片段可能以"："结尾或明显被截断。
    """
    p = root / "sft" / "all.jsonl"
    if not p.exists():
        return {"present": False}
    rows = load_jsonl(p)
    inst = {}
    for layer in ("natural", "synthetic"):
        for r in load_jsonl(root / layer / "instances.jsonl"):
            inst[r["instance_id"]] = r

    import re
    art_re = re.compile(r"第[一二三四五六七八九十百零〇\d]+条")

    def incomplete(text: str) -> int:
        """结尾是冒号/顿号/逗号 = 枚举或句子被切断。用 `_parse_blocks` 取完整正文。"""
        return sum(1 for _, _, body in _parse_blocks(text)
                   if body.rstrip().endswith(_BAD_TAIL))

    out = {
        "present": True,
        "samples": len(rows),
        "by_split": {sp: sum(1 for r in rows if r["split"] == sp)
                     for sp in ("train", "dev", "test")},
        "prompt_chars": _stats([len(r["prompt"]) for r in rows]),
        "completion_chars": _stats([len(r["completion"]) for r in rows]),
        "kinds": dict(Counter(inst.get(r["instance_id"], {}).get("kind") for r in rows)),
    }

    # 1. completion 里的条款号（教模型编造）
    with_art, examples = 0, []
    for r in rows:
        hits = sorted(set(art_re.findall(r["completion"])))
        # 只看**gold 条文**的条款号：模型确实不可能从匿名候选里知道它
        gold = set()
        src = inst.get(r["instance_id"]) or {}
        for v in (src.get("visible_evidence", {}).get("candidate_map") or {}).values():
            gold |= set(art_re.findall(v or ""))
        bad = [h for h in hits if h in gold]
        if bad:
            with_art += 1
            if len(examples) < 3:
                examples.append({"doc": r["meta"]["doc"][:30], "articles": bad})
    out["completion_with_gold_article"] = with_art
    out["completion_article_examples"] = examples

    # 2. 候选里同一条文重复：**必须区分「同一文本」与「同条不同款/项」**
    #    实测教训：早先把「同条不同项」也算成缺陷，得出 51.4% 的假缺陷率。
    #    真冗余（逐字相同）才是缺陷；不同款项本就是不同条文，保留是对的。
    same_text, diff_text, samples_dup = 0, 0, 0
    for r in rows:
        src = inst.get(r["instance_id"]) or {}
        groups: dict[str, list[str]] = {}
        for label, law, body in _parse_blocks(
                src.get("visible_evidence", {}).get("candidates")):
            ref = (src.get("visible_evidence", {}).get("candidate_map") or {}).get(label, "")
            if art_re.search(ref):
                groups.setdefault(ref, []).append(body)
        hit = False
        for texts in groups.values():
            if len(texts) > 1:
                hit = True
                if len(set(texts)) == 1:
                    same_text += 1
                else:
                    diff_text += 1
        if hit:
            samples_dup += 1
    out["dup_article_same_text"] = same_text        # 真冗余，应为 0
    out["dup_article_diff_text"] = diff_text        # 同条不同款/项，非缺陷
    out["samples_with_dup_article"] = samples_dup

    # 3. 残句候选（结尾是冒号/逗号 = 枚举或句子被切断）
    trunc = [incomplete((inst.get(r["instance_id"]) or {})
                        .get("visible_evidence", {}).get("candidates")) for r in rows]
    out["candidates_incomplete_total"] = sum(trunc)
    out["samples_with_incomplete_candidate"] = sum(1 for t in trunc if t)

    # 4. **最重要的一项**：答案引用了残句候选 → 要件在题面里没有依据，
    #    等于教模型凭空输出。实测 v3 为 23.6%，修复后应为 0。
    harmful, hex_ = 0, []
    for r in rows:
        src = inst.get(r["instance_id"]) or {}
        bodies = {label: body for label, _, body in
                  _parse_blocks(src.get("visible_evidence", {}).get("candidates"))}
        cited: set[str] = set()
        for e in (src.get("answer") or {}).get("elements") or []:
            cited |= {x for x in (e.get("evidence_refs") or []) if x.startswith("候选")}
        bad = [c for c in cited if bodies.get(c, "").rstrip().endswith(_BAD_TAIL)]
        if bad:
            harmful += 1
            if len(hex_) < 3:
                hex_.append({"doc": (r["meta"].get("doc") or "")[:30],
                             "candidates": sorted(bad)})
    out["answer_cites_incomplete_candidate"] = harmful
    out["answer_cites_incomplete_examples"] = hex_
    return out


def verdict(a: dict) -> list[str]:
    """把画像转成可读的结论与风险提示。"""
    v: list[str] = []
    s, sig, rw, nq, pq, lk, cv = (a["scale"], a["signal"], a["reward"],
                                  a["negative_quality"], a["pair_quality"],
                                  a["leakage"], a["coverage"])
    v.append(f"规模：{s['instances']} 条实例（正 {s['positive']} / 负 {s['negative']}）"
             f"，{s['preference_pairs']} 对偏好对，覆盖 {s['cases']} 个案件。")
    v.append(f"分层：natural {s['natural']} / synthetic {s['synthetic']}"
             f"（合成占比 {s['synthetic_share']}）。")

    if sig["positives_with_zero_unsatisfied"]:
        pct = sig["positives_with_zero_unsatisfied"] / max(s["positive"], 1)
        v.append(f"⚠️ {sig['positives_with_zero_unsatisfied']} 条正例（{pct:.0%}）"
                 "全部要件满足 —— 这些样本只教「全都算」.")
    else:
        v.append("✅ 每条正例都至少有一个「不满足」要件，样本含判别信息。")

    if nq["discriminative"] == s["negative"]:
        v.append(f"✅ 全部 {s['negative']} 条负例都成功翻转（判别率 100%）。")
    else:
        v.append(f"⚠️ 负例判别 {nq['discriminative']}/{s['negative']}"
                 f"（{nq['discriminative'] / max(s['negative'], 1):.0%}），"
                 "未翻转的负例不产生梯度。")

    if nq["mutations_touching_multiple_facts"]:
        v.append(f"ℹ️ {nq['mutations_touching_multiple_facts']} 条负例为多事实突变"
                 "（要件由多条事实支撑时必须全部反转）。")

    sat = rw["r_soft_saturated_at_1"]
    if sat:
        v.append(f"⚠️ **{sat}/{s['instances']} 条实例 r_soft = 1.0（饱和）** —— "
                 "现有 verifier 只检查格式完备性，不检查答案质量，"
                 "**对 RL 没有梯度**（Rubric 层按 OPEN-7 = A 未实现）。SFT 不受影响。")

    if pq["pairs_with_zero_gap"]:
        v.append(f"❌ {pq['pairs_with_zero_gap']} 对偏好对 reward 落差为 0 —— 验证器没拦下")
    else:
        v.append(f"✅ 全部 {s['preference_pairs']} 对偏好对都有正的 reward 落差"
                 f"（中位 {pq['reward_gap'].get('median')}）。")

    for k, label in (("article_leak", "条款号泄漏"),
                     ("question_shared_across_cases", "题干跨案件复用"),
                     ("multiple_positives_same_question", "同一题干多个正例"),
                     ("duplicate_visible_evidence", "重复可见证据"),
                     ("duplicate_instance_ids", "重复实例 ID")):
        if lk.get(k):
            v.append(f"❌ {label}：{lk[k]}")
    if not any(lk.get(k) for k in ("article_leak", "question_shared_across_cases",
                                   "multiple_positives_same_question",
                                   "duplicate_visible_evidence",
                                   "duplicate_instance_ids")):
        v.append("✅ 无条款号泄漏、无跨案件题干复用、无重复证据/实例 ID。")
    if lk.get("negatives_reusing_positive_question"):
        v.append(f"ℹ️ {lk['negatives_reusing_positive_question']} 条负例复用正例题干"
                 f"（OPEN-4 = b 的设计要求，非缺陷）；去重后题干 {lk['distinct_questions']} 条。")
    if lk.get("law_name_in_question"):
        v.append(f"ℹ️ {lk['law_name_in_question']} 条题干出现法规名。"
                 "V3 下候选条文自带法规名，不构成泄漏，但若总是复述同一候选等于给了提示。")

    v.append(f"覆盖：{cv['distinct_candidate_norms']} 部不同条文、"
             f"{cv['distinct_visible_nodes']} 个可见证据节点。")
    return v


def main() -> int:
    # Windows 控制台默认 GBK，打印 ⚠️/✅ 会抛 UnicodeEncodeError
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    root = Path(sys.argv[1])
    a = analyse(root)
    # 可选第二参数：把画像 JSON 以 UTF-8 落盘（不要用 PowerShell 重定向，
    # 那会写成 UTF-16，读的时候会 UnicodeDecodeError）
    if len(sys.argv) > 2:
        out = Path(sys.argv[2])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(a, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"画像已写入 {out}", file=sys.stderr)
    print(json.dumps(a, ensure_ascii=False, indent=2))
    print("\n" + "=" * 70)
    print("质量结论")
    print("=" * 70)
    for line in verdict(a):
        print("· " + line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
