#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署 pipeline.py 的"死代码清理"版（第二批收尾）。

改了什么：删掉 `ABOLISHED_STATUS` —— 它在第二批里定义后**从未被使用**
（真正生效的是 `source_block()` 把 status/status_note 直接写进资料块）。
删它不改变任何行为，但留着一个"看起来在判废止、其实没人调"的常量很危险：
下一个人会以为检索降权是它做的。

行为不变怎么证明（不靠"我觉得"）：
  ① 语法编译；
  ② 交付前先备份，可一条命令回滚；
  ③ 部署后由 `查嵌入契约.py` 的 [5c] 节**真跑 source_block()** 断言
     资料块仍带「时效状态：已废止 —— 依据」（exec 出函数本体来渲染，不是字符串匹配）。
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time

HOST = "10.201.31.10"
LOCAL = r"服务器会话\xishu_site\xishu_pipeline\pipeline.py"
REMOTE = "/home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py"
STAMP = time.strftime("%Y%m%d_%H%M%S")
BAK = "/home/test/_重构归档_20260922/第二批_前/pipeline.py.%s" % STAMP
HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUT = os.path.join(HERE, "服务器会话", "put_file.py")
RUN = os.path.join(HERE, "服务器会话", "runcmd.py")


def sh(args: list) -> str:
    r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        raise SystemExit("命令失败：%s" % " ".join(args[:2]))
    return (r.stdout or "") + (r.stderr or "")


def main() -> int:
    with open(os.path.join(HERE, LOCAL), encoding="utf-8") as fh:
        src = fh.read()
    if "ABOLISHED_STATUS" in src:
        raise SystemExit("本地文件里还有 ABOLISHED_STATUS，先改干净")
    md5 = hashlib.md5(src.encode("utf-8")).hexdigest()
    print("本地：%s（%d 字节，md5 %s）" % (LOCAL, len(src.encode('utf-8')), md5))

    print("\n[1] 线上现状（备份前）")
    print(sh([RUN, "--host", HOST, "--timeout", "120",
              "grep -c ABOLISHED_STATUS %s; md5sum %s" % (REMOTE, REMOTE)]).strip())

    print("\n[2] 备份 + 上传")
    print(sh([RUN, "--host", HOST, "--timeout", "180",
              "cp -p %s %s && ls -l %s" % (REMOTE, BAK, BAK)]).strip())
    print(sh([PUT, "--host", HOST, os.path.join(HERE, LOCAL), REMOTE]).strip())
    print(sh([RUN, "--host", HOST, "--timeout", "120",
              "md5sum %s; grep -c ABOLISHED_STATUS %s || echo '常量已清除'" % (REMOTE, REMOTE)]).strip())

    print("\n[3] 重启")
    print(sh([RUN, "--host", HOST, "--timeout", "600",
              "bash /home/test/安全重启8011.sh 2>&1 | tail -4"]).strip())
    print("\n回滚：cp -p %s %s && bash /home/test/安全重启8011.sh" % (BAK, REMOTE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
