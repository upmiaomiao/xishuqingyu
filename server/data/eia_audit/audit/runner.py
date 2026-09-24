#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核流程的可复用入口（CLI 与网页共用同一份逻辑，避免两套实现跑偏）。

路径全部自适应，且**不依赖启动脚本注入环境变量**（启动脚本 md5 冻结）：
  判据目录：EIA_CRITERIA_DIR → 工作区 `判据库/` → `/data/fagui_rag/criteria`
  报告目录：AUDIT_REPORT_DIR → 工作区 环评报告/环评报告/环评报告 → `/data/eia_reports`
  解析缓存：AUDIT_CACHE_DIR → 脚本旁 `_cache` → `/data/eia_audit/cache`
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PKG_ROOT = os.path.dirname(HERE)
sys.path.insert(0, PKG_ROOT)

from audit.criteria import Criteria  # noqa: E402
from audit.extract import extract_all, map_to_catalog_terms, project_digest  # noqa: E402
from audit.extract_llm import llm_conditions, llm_inputs  # noqa: E402
from audit.judge import judge_report, pick_item  # noqa: E402
from audit.parse import load_or_parse  # noqa: E402

STATE_ICON = {"存在问题": "[X]", "存在疑似问题": "[?]", "优化调整建议": "[~]",
              "无问题": "[v]", "不适用": "[-]"}
SPECIAL_KEYS = ["废水是否直排", "是否新增河道取水",
                "是否涉及集中式饮用水水源或特殊地下水资源保护区",
                "厂界外500米内是否有环境空气保护目标",
                "取水口下游500米内是否有重要水生生物三场一通道"]


def _first_dir(cands: list, create: str = None) -> str:
    """取第一个存在的目录；都不存在时才尝试创建（创建失败不抛异常）。"""
    for c in cands:
        if c and os.path.isdir(c):
            return c
    for c in cands:
        if c:
            try:
                os.makedirs(c, exist_ok=True)
                return c
            except Exception:
                continue
    return create or (cands[0] if cands else "")


def report_dir() -> str:
    # PKG_ROOT 是「审核智能体」目录，上两级才是工作区根
    ws = os.path.dirname(os.path.dirname(PKG_ROOT))
    return _first_dir([
        os.environ.get("AUDIT_REPORT_DIR") or "",
        os.path.join(ws, "环评报告", "环评报告", "环评报告"),
        "/data/eia_reports",
    ])


def cache_dir() -> str:
    return _first_dir([os.environ.get("AUDIT_CACHE_DIR") or "",
                       os.path.join(PKG_ROOT, "_cache"),
                       "/data/eia_audit/cache"])


def list_reports(only_unique: bool = True) -> list:
    root = report_dir()
    if not os.path.isdir(root):
        return []
    names = sorted(f for f in os.listdir(root) if f.lower().endswith(".pdf"))
    if only_unique:
        # 同内容重复件只留一份。这里直接对**文件字节**取 sha1：
        # 早先写成"解析一遍再取 sha1"，为了列个清单要把 8 份报告全解析一遍，太慢。
        import hashlib
        seen, out = set(), []
        for n in names:
            try:
                with open(os.path.join(root, n), "rb") as f:
                    h = hashlib.sha1(f.read()).hexdigest()
            except Exception:
                h = n
            if h in seen:
                continue
            seen.add(h)
            out.append(n)
        return out
    return names


def audit_file(pdf_path: str, use_llm: bool = True, verbose: bool = False,
               C: Criteria = None) -> dict:
    """对一份报告跑完整审核，返回与截图同构的结果字典。"""
    C = C or Criteria()
    rep = load_or_parse(pdf_path, cache_dir=cache_dir())
    ex = extract_all(rep, verbose=False)
    llm_in, cond_facts = {}, []
    if use_llm:
        item0 = pick_item(ex, C)
        if item0 and verbose:
            print(f"    名录候选：序号{item0['no']} {item0['category'][:40]}")
        if item0:
            stated = ex.basic.get("名录条目")
            cond_facts = llm_conditions(rep, item0, cache_dir=cache_dir(), verbose=verbose,
                                        digest=project_digest(rep, ex),
                                        stated=(stated.value if stated else ""),
                                        stated_page=(stated.page if stated else None))
        skip = {k for k, v in ex.special_inputs.items()
                if isinstance(v, dict) and v.get("method") == "table" and v.get("value") is not None}
        llm_in = llm_inputs(rep, cache_dir=cache_dir(), keys=SPECIAL_KEYS,
                            skip=skip, verbose=verbose)
        for k, v in llm_in.items():
            if v.get("value") is not None and v.get("_verified"):
                ex.special_inputs[k] = {"value": v["value"], "page": v.get("page"),
                                        "quote": v.get("quote", ""), "method": "llm"}
    res = judge_report(rep, ex, C, llm_in, cond_facts=cond_facts, verbose=verbose)
    res["抽取概况"] = {
        "物料": len(ex.materials), "风险物质": len(ex.risk_materials),
        "敏感目标": len(ex.sensitive_targets),
        "名录用语归属": {k: {"合计": v["total"], "单位": v["unit"], "依据": v["basis"]}
                         for k, v in map_to_catalog_terms(ex.materials)["buckets"].items()},
    }
    res["报告自述"] = {k: (f.value if f else None) for k, f in ex.basic.items()}
    res["专项评价自述"] = ex.special_stated
    res["抽取明细"] = {
        "物料": ex.materials[:60],
        "风险物质": ex.risk_materials[:60],
        "敏感目标": ex.sensitive_targets[:60],
        "条件事实": cond_facts,
    }
    return res


def print_result(res: dict, verbose: bool = True):
    f = res["file"]
    print(f"\n=== {f['name'][:60]}")
    print(f"    类型={f['环评文件类型']}  项目={str(f['项目名称'])[:40]}")
    print(f"    物料 {res['抽取概况']['物料']} 项；名录用语归属："
          f"{res['抽取概况']['名录用语归属'] or '无'}")
    for it in res["items"]:
        print(f"    {STATE_ICON.get(it['AI审核'], '?')} {it['审核项']:22s} {it['AI审核']:8s} "
              f"{it['环评文件'] or '':7s} {it['理由'][:64]}")
        for c in it["需人工确认"]:
            print(f"        ! 需人工确认：{c[:88]}")
    for c in res["冲突"]:
        print(f"    !! 输入冲突（正则 vs 模型）：{c['输入']} "
              f"正则={c['正则']} 模型={c['模型']}")