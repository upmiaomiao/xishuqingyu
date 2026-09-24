#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P4：把 `服务器会话/` 里的脚本按用途归档到子目录（**只移动，不删除**）。

用法：
  python archive_ops.py --dry-run          # 只打印归属，不动文件
  python archive_ops.py --apply            # 真正移动，并生成回滚脚本与清单

设计要点：
  · 只移动，不删除任何用户文件；`__pycache__` 属可再生成的缓存，单独处理。
  · 明确列出"覆盖名单"（文件名特殊、按前缀会分错的），避免机械分类把文件放错。
  · 生成 restore_ops.py：一键把文件搬回原位。
  · 生成 归档清单.md：移动前/后路径逐行可查。
"""
from __future__ import annotations

import json
import os
import shutil
import sys

D = r"D:\项目\中节能\0911训练\服务器会话"
APPLY = "--apply" in sys.argv

# 保留在顶层：基础设施常驻工具 + 心跳日志（脚本按原路径写日志，移动会导致日志分裂）
TOP_KEEP = {
    "rsh.py", "put_file.py", "get_file.py", "runcmd.py", "push_env.py",
    "keepalive_12.py", "keepalive_12.log",
}

# 明确指定归属（优先级最高）——这些按前缀会被分错
EXPLICIT = {
    # 服务端：源码、快照、部署与"改线上"的脚本
    "xishu_qingyu_qa_线上版.py": "服务端",
    "网站切v5部署说明.md": "服务端",
    "launch_vllm_v5_prod.sh": "服务端",
    "switch_site_to_v5.py": "服务端",
    "verify_site_v5.py": "服务端",
    "raise_max_tokens.py": "服务端",
    "fix_and_cleanup.py": "服务端",
    "fix_identity_sample.py": "服务端",
    "debug_splitter.py": "服务端",
    "test_answer_splitter.py": "服务端",
    "test_routing.py": "服务端",
    "repro_answer_tag.py": "服务端",
    "hunt_answer_tag.py": "服务端",
    "test_multi_turn.py": "服务端",
    "repro_multi_turn.py": "服务端",
    "verify_router.py": "服务端",
    "verify_sse.py": "服务端",
    "compare_tone.py": "服务端",
    "check_side_effects.py": "服务端",
    "check_ctx.py": "服务端",
    "check_ctx2.py": "服务端",
    "test_audit_clean.py": "服务端",
    # 训练与评测
    "训练进度_merged_wte_v5.md": "训练与评测",
    "run_swift_merged_wte.sh": "训练与评测",
    "upload_merged.py": "训练与评测",
    "monitor_cycle.py": "训练与评测",
    "monitor_state.json": "训练与评测",
    "export_v5.py": "训练与评测",
    "cleanup_eval_instances.py": "训练与评测",
    # 案例生成
    "scan_everyday.py": "案例生成",
    "look_everyday.py": "案例生成",
    "look_demo.py": "案例生成",
    "look_final.py": "案例生成",
    "scan_realistic_pro.py": "案例生成",
    "scan_realistic_pro2.py": "案例生成",
    "scan_realistic_pro3.py": "案例生成",
    "scan_factual.py": "案例生成",
}

# 按前缀兜底
PREFIX_RULES = [
    (("judge_", "run_609", "launch_eval", "launch_base_eval", "gen_eval_report",
      "gen_unified_report", "recheck_base", "sample_wte_tests", "run_wte_tests",
      "wte_retest_constr", "check_recall_vs_fabrication", "verify_fabrication",
      "audit_train_numbers", "disk_survey_12", "check_env_12"), "训练与评测"),
    (("run_everyday", "run_pro", "pick_golden"), "案例生成"),
    (("check_", "verify_", "probe_", "diag_", "dissect_", "test_", "look_",
      "repro_", "compare_"), "排查验证"),
]

BUCKETS = ["服务端", "训练与评测", "案例生成", "排查验证"]


def classify(name: str) -> str | None:
    if name in TOP_KEEP:
        return None
    if name in EXPLICIT:
        return EXPLICIT[name]
    for prefixes, bucket in PREFIX_RULES:
        if name.startswith(prefixes):
            return bucket
    return "未分类"


def main() -> None:
    files = sorted(f for f in os.listdir(D) if os.path.isfile(os.path.join(D, f)))
    plan: dict[str, list[str]] = {b: [] for b in BUCKETS}
    unclassified: list[str] = []
    for f in files:
        b = classify(f)
        if b is None:
            continue
        if b == "未分类":
            unclassified.append(f)
        else:
            plan[b].append(f)

    print(f"顶层文件 {len(files)} 个；保留顶层 {len(TOP_KEEP & set(files))} 个")
    total = 0
    for b in BUCKETS:
        print(f"\n【{b}】{len(plan[b])} 个")
        for f in plan[b]:
            print(f"    {f}")
        total += len(plan[b])
    print(f"\n【未分类】{len(unclassified)} 个")
    for f in unclassified:
        print(f"    {f}")
    print(f"\n合计将移动 {total} 个")

    if not APPLY:
        print("\n（dry-run，未改动任何文件）")
        return

    moves = []
    for b in BUCKETS:
        os.makedirs(os.path.join(D, b), exist_ok=True)
        for f in plan[b]:
            src, dst = os.path.join(D, f), os.path.join(D, b, f)
            shutil.move(src, dst)
            moves.append({"from": f, "to": f"{b}/{f}"})

    # 回滚脚本
    restore = os.path.join(D, "restore_ops.py")
    with open(restore, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('#!/usr/bin/env python3\n# -*- coding: utf-8 -*-\n'
                 '"""P4 归档的回滚脚本：把文件按清单搬回 `服务器会话/` 顶层。"""\n'
                 'import os, shutil\n\n'
                 f'D = r"{D}"\n'
                 f'MOVES = {json.dumps(moves, ensure_ascii=False, indent=2)}\n\n'
                 'for m in MOVES:\n'
                 '    src = os.path.join(D, m["to"])\n'
                 '    dst = os.path.join(D, m["from"])\n'
                 '    if os.path.isfile(src):\n'
                 '        shutil.move(src, dst)\n'
                 '        print("还原", m["to"], "->", m["from"])\n'
                 'for b in ["服务端", "训练与评测", "案例生成", "排查验证"]:\n'
                 '    p = os.path.join(D, b)\n'
                 '    if os.path.isdir(p) and not os.listdir(p):\n'
                 '        os.rmdir(p)\n')
    print(f"\n已移动 {len(moves)} 个文件；回滚脚本：{restore}")

    # 归档清单（人工可查）
    manifest = os.path.join(D, "归档清单.md")
    lines = ["# `服务器会话/` 归档清单（P4）", "",
             f"共移动 **{len(moves)}** 个文件；顶层保留基础设施工具与心跳日志。", "",
             "| 文件 | 移动前 | 移动后 |", "| --- | --- | --- |"]
    for m in moves:
        lines.append(f"| `{m['from']}` | `服务器会话/` | `服务器会话/{m['to']}` |")
    lines += ["", "## 回滚", "",
              "```powershell",
              "python \"<工作区>\\服务器会话\\restore_ops.py\"",
              "```", "",
              "> 生成脚本：`_脚本代码/格式转换/archive_ops.py`（`--dry-run` 可重新预演）。"]
    open(manifest, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
    print(f"归档清单：{manifest}")


if __name__ == "__main__":
    main()
