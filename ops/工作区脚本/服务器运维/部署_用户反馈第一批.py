#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户反馈第一批修复的部署脚本（先暂存 + 打差异，加 --apply 才真正切换）。

为什么要"先看差异再切换"：这些文件各有权威副本、且线上是活的；
一旦覆盖错了（比如把旧归档当部署源），线上看着"正常"、不会报错。
所以顺序固定为：上传到 _staging → 与线上逐字节 diff → 备份 → 切换 → 语法/导入自检。

用法：
  python 部署_用户反馈第一批.py            # 只上传暂存 + 打印差异（只读线上）
  python 部署_用户反馈第一批.py --apply    # 备份 + 切换（不含重启，重启单独一步）
"""
from __future__ import annotations

import difflib
import os
import sys
from pathlib import Path

import paramiko

HOST = "10.201.31.10"
HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
sys.path.insert(0, str(WS / "服务器会话"))
from rsh import parse_creds  # noqa: E402

STAGE = "/home/test/_staging_20260922_第一批"
BAK = "/home/test/_重构归档_20260922/第一批_前"
LIVE_ROOT = "/home/test/xishu_qingyu_serve/"


def stage_of(live: str) -> str:
    """暂存路径与线上路径一一对应（去掉 LIVE_ROOT 前缀，或按 data 目录归类）。"""
    if live.startswith(LIVE_ROOT):
        return STAGE + "/" + live[len(LIVE_ROOT):]
    if live.startswith("/data/eia_audit/"):
        return STAGE + "/audit/" + live[len("/data/eia_audit/audit/"):]
    if live.startswith("/data/eia_report_gen/"):
        return STAGE + "/gen/" + live[len("/data/eia_report_gen/gen/"):]
    raise ValueError("不知道怎么映射：" + live)


# (本地文件, 线上文件, 说明)
FILES = [
    ("_脚本代码/审核智能体/audit/criteria.py",
     "/data/eia_audit/audit/criteria.py",
     "审核判据：空输入不判『符合要求』（环境风险／大气）"),
    ("_脚本代码/报告生成/gen/intake.py",
     "/data/eia_report_gen/gen/intake.py",
     "报告编制：枚举归一（不再整份被拒）＋『纳管/进园区』等价否定"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js",
     "编制界面：回车发送＋输入法守卫；新建报告残留复位"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js",
     "审核界面：『不适用』口径说明"),
    ("_脚本代码/审核智能体/服务端/static/audit_ui.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.css",
     "审核界面：口径说明样式"),
    ("_脚本代码/审核智能体/服务端/audit_docx.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/audit_docx.py",
     "意见书：把『不适用』口径写进交付件"),
    ("服务器会话/xishu_site/frontend/js/main.js",
     "/home/test/xishu_qingyu_serve/frontend/js/main.js",
     "问答页：输入法选词的回车不当发送"),
]


def main():
    apply_ = "--apply" in sys.argv
    user, pw = parse_creds(str(WS / "账号.md"))[HOST]
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, 22, user, pw, timeout=20, look_for_keys=False, allow_agent=False)
    sftp = cli.open_sftp()

    def sh(cmd: str) -> str:
        _in, out, err = cli.exec_command(cmd, timeout=120)
        return out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")

    print("===== 0) 建暂存/备份目录 =====")
    print(sh(f"mkdir -p {STAGE}/{{audit,gen,xishu_pipeline/static,frontend/js}} {BAK} && echo ok"))

    print("===== 1) 上传到暂存（CRLF→LF）=====")
    for rel, rem, note in FILES:
        local = WS / rel
        data = local.read_bytes().replace(b"\r\n", b"\n")
        stage_path = stage_of(rem)
        with sftp.open(stage_path, "wb") as f:
            f.write(data)
        print(f"  {len(data):7d} B  {stage_path}   ← {rel}")
        print(f"           {note}")

    print("\n===== 2) 与线上逐字节差异（只读）=====")
    pairs = [(stage_of(rem), rem) for _rel, rem, _n in FILES]
    for s, live in pairs:
        n = sh(f"diff -u '{live}' '{s}' | wc -l").strip()
        adds = sh(f"diff -u '{live}' '{s}' | grep -c '^+[^+]' || true").strip()
        dels = sh(f"diff -u '{live}' '{s}' | grep -c '^-[^-]' || true").strip()
        print(f"  {os.path.basename(live):18s} diff 行数={n:>5s}  +{adds} -{dels}   {live}")

    print("\n===== 3) 完整差异（新增/删除行，供人工确认）=====")
    for s, live in pairs:
        d = sh(f"diff -u '{live}' '{s}' | head -120")
        if d.strip():
            print(f"\n---------- {live}")
            print(d)

    if not apply_:
        print("\n（未加 --apply：只上传了暂存、没有改动线上任何文件）")
        sftp.close()
        cli.close()
        return 0

    print("\n===== 4) 备份线上文件 =====")
    stamp = sh("date +%Y%m%d_%H%M%S").strip()
    baks = [
        ("/data/eia_audit/audit/criteria.py", "criteria.py"),
        ("/data/eia_report_gen/gen/intake.py", "intake.py"),
        ("/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js", "gen_ui.js"),
        ("/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js", "audit_ui.js"),
        ("/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.css", "audit_ui.css"),
        ("/home/test/xishu_qingyu_serve/xishu_pipeline/audit_docx.py", "audit_docx.py"),
        ("/home/test/xishu_qingyu_serve/frontend/js/main.js", "main.js"),
    ]
    for live, name in baks:
        print(sh(f"cp -p '{live}' '{BAK}/{name}.{stamp}' && cmp -s '{BAK}/{name}.{stamp}' '{live}' "
                 f"&& echo '  备份一致 {name}' || echo '  备份失败 {name}'").strip())
    print(sh(f"md5sum {BAK}/*.{stamp}"))

    print("\n===== 5) 切换 =====")
    for s, live in pairs:
        print(sh(f"cp '{s}' '{live}' && echo '已切换 {live}'").strip())

    print("\n===== 6) 自检（语法 + 真实 import）=====")
    PY = "/home/test/fagui_serve/.venv/bin/python"
    for live, name in baks:
        if live.endswith(".py"):
            print(sh(f"{PY} -m py_compile '{live}' && echo '  语法 OK {name}'").strip())
    print(sh("command -v node >/dev/null && for f in "
             "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js "
             "/home/test/xishu_qingyu_serve/frontend/js/main.js "
             "/home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js; do "
             "node --check \"$f\" && echo \"  js 语法 OK $f\"; done || echo '(服务器无 node，跳过 js 语法检查)'"))
    print(sh(f"cd /home/test/xishu_qingyu_serve && {PY} -c "
             "\"import sys; sys.path.insert(0,'/home/test/xishu_qingyu_serve');"
             "import xishu_pipeline.audit_docx as d; print('  audit_docx import OK')\" 2>&1 | tail -3"))
    print(sh(f"cd /data/eia_report_gen && {PY} -c "
             "\"import sys; sys.path.insert(0,'/data/eia_report_gen');"
             "from gen import intake; print('  gen.intake import OK; NEG_CUES=', len(intake.NEG_CUES),"
             "'EQUIV=', len(intake.EQUIV_NEG_CUES))\" 2>&1 | tail -3"))
    print(sh(f"cd /data/eia_audit && {PY} -c "
             "\"import sys; sys.path.insert(0,'/data/eia_audit');"
             "from audit.criteria import Criteria; C=Criteria();"
             "r=C.eval_risk_special([]); print('  audit.criteria import OK; 空清单 →', r['status'])\" 2>&1 | tail -3"))

    print("\n===== 7) 指纹 =====")
    for live, _n in baks:
        print(sh(f"md5sum '{live}'").strip())
    sftp.close()
    cli.close()
    print("\n完成。重启请单独执行：bash /home/test/安全重启8011.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
