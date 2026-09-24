#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三批部署：GB 8978 元数据修正的索引 + 检索器"标准号硬命中"。

改了哪两处、为什么（详细论证见 `_工作记录/2026-09-22-第三批-B5根因与修法.md`）：
  ① 索引 `/data/fagui_rag/index_v6_8978`：GB 8978-1996 那份（30 块）由「已废止」改回「现行」
     —— 官方登记（全国标准信息公共服务平台）为"强制性 现行"，只是被 GB 20425/20426 **部分代替**。
     库里错标成"已废止"，而检索器对已废止扣 0.35 分，等于**把唯一带规则原文的那份压下去**。
  ② 检索器 `retriever.py`：题面点名标准号（GB/HJ/DB + 数字）时，
     把该标准自己的块注入候选池，并保证最终引用至少 1 块来自它。
     实测 B5 的问法召回 72 块里 8978 的块是 **0 条** —— 不是排序问题，是根本没进池。
     可用 `RAG_STD_PIN=0` 一键关掉回滚。

顺序：备份 → 上传 → 语法+import 自检 → 切索引 → 重启 → 探针复核。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time

HOST = "10.201.31.10"
LOCAL_RET = r"服务器会话\服务端\rag\retriever.py"
REMOTE_RET = "/data/fagui_rag/retriever.py"
NEW_INDEX = "/data/fagui_rag/index_v6_8978"
STAMP = time.strftime("%Y%m%d_%H%M%S")
BAK = "/home/test/_重构归档_20260922/第三批_前"
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUT = os.path.join(HERE, "服务器会话", "put_file.py")
RUN = os.path.join(HERE, "服务器会话", "runcmd.py")


def sh(args: list) -> str:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit("命令失败：%s" % " ".join(a for a in args[:2]))
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    src = open(os.path.join(HERE, LOCAL_RET), encoding="utf-8").read()
    for token in ("def codes_in", "def code_of", "STD_PIN_ON", "pins=codes", "codes=codes"):
        if token not in src:
            raise SystemExit("本地 retriever.py 缺关键片段：%s" % token)
    print("本地 retriever.py：%d 字节，md5 %s"
          % (len(src.encode("utf-8")), hashlib.md5(src.encode("utf-8")).hexdigest()))

    print("\n[1] 备份线上检索器")
    print(sh([RUN, "--host", HOST, "--timeout", "180",
              "mkdir -p %s && cp -p %s %s/retriever.py.%s && ls -l %s/retriever.py.%s"
              % (BAK, REMOTE_RET, BAK, STAMP, BAK, STAMP)]).strip())

    print("\n[2] 上传 + 自检")
    print(sh([PUT, "--host", HOST, os.path.join(HERE, LOCAL_RET), REMOTE_RET]).strip())
    print(sh([RUN, "--host", HOST, "--timeout", "300",
              "cd /data/fagui_rag && /home/test/fagui_serve/.venv/bin/python -c "
              "\"import retriever as R; print('import OK');"
              "print('codes_in:', sorted(R.codes_in('GB8978总汞 0.05 mg/L 三级标准吗')));"
              "print('pin on:', R.STD_PIN_ON, R.STD_PIN_POOL, R.STD_PIN_FINAL)\" 2>&1 | tail -4"]).strip())

    print("\n[3] 切索引")
    print(sh([RUN, "--host", HOST, "--timeout", "600",
              "bash /home/test/切换索引.sh %s 2>&1 | tail -8" % NEW_INDEX]).strip())

    print("\n[4] 重启")
    print(sh([RUN, "--host", HOST, "--timeout", "600",
              "bash /home/test/安全重启8011.sh 2>&1 | tail -4"]).strip())

    print("\n回滚：")
    print("  cp -p %s/retriever.py.%s %s" % (BAK, STAMP, REMOTE_RET))
    print("  索引切回：bash /home/test/切换索引.sh /data/fagui_rag/index.bak_before_*  ")
    print("  或临时关掉硬命中：RAG_STD_PIN=0 后重启")
    return 0


if __name__ == "__main__":
    sys.exit(main())
