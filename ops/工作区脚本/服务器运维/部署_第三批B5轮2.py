#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三批第二轮部署：检索器"标准号硬命中"改进版 + 提示词"证据类型"规则。

第一版实测出来的问题（必须记下来，否则下次还会踩）：
  只按相似度把被点名标准的块补进池子 → 补进来的是《污水综合排放标准》的
  **标准分级**块（讲一级/二级/三级），模型据此答"存在三级标准"，比不改还糟。
  真正要的是含"第一类污染物／车间排放口／总汞"**字面**的条文块，而条文式文本
  与口语化提问的语义相似度天生偏低 → 改为**字面重合优先、相似度次之**，
  且最终引用位也从同一排序里取（STD_PIN_FINAL=2）。
配套提示词规则：标准本体问题（分级/采样口/限值）只认标准原文，
报告的"执行三级标准"是转述，不能反推标准分类。

用法：python 部署_第三批B5轮2.py
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

HOST = "10.201.31.10"
PAIRS = [
    (r"服务器会话\服务端\rag\retriever.py", "/data/fagui_rag/retriever.py"),
    (r"服务器会话\xishu_site\xishu_pipeline\pipeline.py",
     "/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py"),
]
BAK = "/home/test/_重构归档_20260922/第三批_前"
STAMP = time.strftime("%Y%m%d_%H%M%S")
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUT = os.path.join(HERE, "服务器会话", "put_file.py")
RUN = os.path.join(HERE, "服务器会话", "runcmd.py")


def sh(args: list) -> str:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("失败：%s" % args[1])
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    ret = open(os.path.join(HERE, PAIRS[0][0]), encoding="utf-8").read()
    for token in ("query_terms", "pin_key", "STD_PIN_FINAL = int", "terms=terms"):
        if token not in ret:
            raise SystemExit("retriever.py 缺关键片段：%s" % token)
    pipe = open(os.path.join(HERE, PAIRS[1][0]), encoding="utf-8").read()
    if "报告转述" not in pipe or "标准本体问题" not in pipe:
        raise SystemExit("pipeline.py 缺新增的证据类型规则")
    print("本地：retriever %d 字节 md5 %s" % (len(ret.encode()), hashlib.md5(ret.encode()).hexdigest()))
    print("本地：pipeline  %d 字节 md5 %s" % (len(pipe.encode()), hashlib.md5(pipe.encode()).hexdigest()))

    print("\n[1] 备份")
    cmds = ["mkdir -p %s" % BAK]
    for _, remote in PAIRS:
        cmds.append("cp -p %s %s/%s.%s" % (remote, BAK, os.path.basename(remote), STAMP))
    print(sh([RUN, "--host", HOST, "--timeout", "300", " && ".join(cmds)]).strip())

    print("\n[2] 上传")
    for local, remote in PAIRS:
        print(sh([PUT, "--host", HOST, os.path.join(HERE, local), remote]).strip()[:200])

    print("\n[3] 语法自检")
    print(sh([RUN, "--host", HOST, "--timeout", "300",
              "cd /data/fagui_rag && /home/test/fagui_serve/.venv/bin/python -m py_compile retriever.py "
              "&& /home/test/fagui_serve/.venv/bin/python -c \"import retriever as R;"
              "print('pin', R.STD_PIN_ON, R.STD_PIN_POOL, R.STD_PIN_FINAL);"
              "print('bigram', sorted(R._bigrams('第一类污染物在车间排放口采样'))[:4])\" "
              "&& /home/test/fagui_serve/.venv/bin/python -m py_compile "
              "/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py && echo 自检通过 2>&1 | tail -4"]).strip())

    print("\n[4] 重启")
    print(sh([RUN, "--host", HOST, "--timeout", "600",
              "bash /home/test/安全重启8011.sh 2>&1 | tail -3"]).strip())
    print("\n回滚：cp -p %s/{retriever.py,pipeline.py}.%s 回原位后重启" % (BAK, STAMP))
    return 0


if __name__ == "__main__":
    sys.exit(main())
