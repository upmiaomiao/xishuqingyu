#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用户反馈第二批修复的部署脚本（先暂存 + 打差异，加 --apply 才真正切换）。

与第一批同一套纪律：上传到 _staging → 与线上逐字节 diff → 备份 → 切换 → 语法/导入自检。
本批内容：
  · A3 废气清单串页（audit/extract.py 裸氨→氨(?!氮)、识别废水表述；audit/items_extra.py 挂"需人工核对"）
  · C6 判定摘要卡片（gen_routes.py 返回体带当前判定；gen_ui.js 只读卡片）
  · C4 生成日志折叠成「生成详情」（gen_ui.js / gen_ui.css 由宿主页决定，先只动 js）

用法：
  python 部署_用户反馈第二批.py            # 只上传暂存 + 打印差异（只读线上）
  python 部署_用户反馈第二批.py --apply    # 备份 + 切换（重启单独一步）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

HOST = "10.201.31.10"
HERE = Path(__file__).resolve().parent
WS = HERE.parents[1]
sys.path.insert(0, str(WS / "服务器会话"))
from rsh import parse_creds  # noqa: E402

STAGE = "/home/test/_staging_20260922_第二批"
BAK = "/home/test/_重构归档_20260922/第二批_前"
LIVE_ROOT = "/home/test/xishu_qingyu_serve/"


def stage_of(live: str) -> str:
    if live.startswith(LIVE_ROOT):
        return STAGE + "/" + live[len(LIVE_ROOT):]
    if live.startswith("/data/eia_audit/"):
        return STAGE + "/audit/" + live[len("/data/eia_audit/audit/"):]
    if live.startswith("/data/eia_report_gen/"):
        return STAGE + "/gen/" + live[len("/data/eia_report_gen/gen/"):]
    raise ValueError("不知道怎么映射：" + live)


# (本地文件, 线上文件, 说明)
FILES = [
    ("_脚本代码/审核智能体/audit/extract.py",
     "/data/eia_audit/audit/extract.py",
     "A3：废气清单——裸「氨」改 氨(?!氮)、识别废水标准号/水质指标（串页嫌疑）"),
    ("_脚本代码/审核智能体/audit/items_extra.py",
     "/data/eia_audit/audit/items_extra.py",
     "A3：大气专项——清单疑似混入废水内容时挂「需人工核对」并给页码"),
    ("服务器会话/xishu_site/xishu_pipeline/pipeline.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py",
     "B1/B2 真根因：给模型的资料块带上索引元数据（标准号/类型/时效状态）+"
     "system 里加「已废止只能作历史参考，不得说仍有效」；"
     "status_note（废止依据）也一并带进资料块"),
    ("_脚本代码/报告生成/服务端/gen_routes.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py",
     "C6：②判定一做完就把判定放进任务（原先只在 done 时才给，生成过程中前端看不到）"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.js",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js",
     "C4 日志折叠成「生成详情」（使用步骤留在外面、出错自动展开）"
     "＋C6 判定摘要只读卡片（轮询即时刷新）"),
    ("_脚本代码/报告生成/服务端/static/gen_ui.css",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css",
     "C4/C6 样式：.ge-logbox/.ge-logsum/.ge-dec*"),
]


def main():
    apply_ = "--apply" in sys.argv
    user, pw = parse_creds(str(WS / "账号.md"))[HOST]
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    cli.connect(HOST, 22, user, pw, timeout=20, look_for_keys=False, allow_agent=False)
    sftp = cli.open_sftp()

    def sh(cmd: str) -> str:
        _in, out, err = cli.exec_command(cmd, timeout=180)
        return out.read().decode("utf-8", "replace") + err.read().decode("utf-8", "replace")

    print("===== 0) 建暂存/备份目录 =====")
    print(sh(f"mkdir -p {STAGE}/audit {STAGE}/xishu_pipeline/static {BAK} && echo ok"))

    print("===== 1) 上传到暂存（CRLF→LF）=====")
    for rel, rem, note in FILES:
        local = WS / rel
        data = local.read_bytes().replace(b"\r\n", b"\n")
        stage_path = stage_of(rem)
        sh(f"mkdir -p '{os.path.dirname(stage_path)}'")
        with sftp.open(stage_path, "wb") as f:
            f.write(data)
        print(f"  {len(data):7d} B  {stage_path}   ← {rel}")
        print(f"           {note}")

    pairs = [(stage_of(rem), rem) for _rel, rem, _n in FILES]

    print("\n===== 2) 与线上逐字节差异（只读）=====")
    for s, live in pairs:
        n = sh(f"diff -u '{live}' '{s}' | wc -l").strip()
        adds = sh(f"diff -u '{live}' '{s}' | grep -c '^+[^+]' || true").strip()
        dels = sh(f"diff -u '{live}' '{s}' | grep -c '^-[^-]' || true").strip()
        print(f"  {os.path.basename(live):18s} diff 行数={n:>5s}  +{adds} -{dels}   {live}")

    print("\n===== 3) 完整差异（供人工确认）=====")
    for s, live in pairs:
        d = sh(f"diff -u '{live}' '{s}' | head -140")
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
    for _rel, live, _n in FILES:
        name = os.path.basename(live)
        print(sh(f"cp -p '{live}' '{BAK}/{name}.{stamp}' && cmp -s '{BAK}/{name}.{stamp}' '{live}' "
                 f"&& echo '  备份一致 {name}' || echo '  备份失败 {name}'").strip())
    print(sh(f"md5sum {BAK}/*.{stamp}"))

    print("\n===== 5) 切换 =====")
    for s, live in pairs:
        print(sh(f"cp '{s}' '{live}' && echo '已切换 {live}'").strip())

    print("\n===== 6) 自检（语法 + 真实 import + 关键行为）=====")
    PY = "/home/test/fagui_serve/.venv/bin/python"
    for _rel, live, _n in FILES:
        if live.endswith(".py"):
            print(sh(f"{PY} -m py_compile '{live}' && echo '  语法 OK {os.path.basename(live)}'").strip())
    print(sh(f"cd /data/eia_audit && {PY} -c \""
             "import sys, inspect; sys.path.insert(0,'/data/eia_audit');"
             "from audit import extract as X;"
             "src = inspect.getsource(X.pollutant_terms);"
             "print('  extract import OK；配方含 氨(?!氮) ->', '氨(?!氮)' in src,"
             " '；含废水标准号识别 ->', hasattr(X, 'WATER_STD_RX'))\" 2>&1 | tail -3"))
    print(sh(f"cd /data/eia_audit && {PY} -c \""
             "import sys; sys.path.insert(0,'/data/eia_audit');"
             "from audit import items_extra as I; print('  items_extra import OK')\" 2>&1 | tail -3"))

    print("\n===== 7) 指纹 =====")
    for _rel, live, _n in FILES:
        print(sh(f"md5sum '{live}'").strip())
    sftp.close()
    cli.close()
    print("\n完成。重启请单独执行：bash /home/test/安全重启8011.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
