#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 Python 解压代码包（Windows 自带 tar.exe 会把 UTF-8 中文名解坏）。

要点：**不走 tarfile.extract()，而是自己 open() 写字节**。
实测在 DSH 文件沙箱下：`tf.extract()` 对包内 140 个成员报 PermissionError（即使把
成员 mode 改成 644 也一样），而同样路径用 `open(...,'wb')` 手写却允许（探针验证过）。
所以这里逐个成员读出来自己落盘，稳。

用法：python 解压代码包.py <tar.gz> <目标目录>
"""
from __future__ import annotations

import os
import sys
import tarfile


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    tgz, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    skipped, done = [], 0
    names = []
    with tarfile.open(tgz, "r:gz") as tf:
        for m in tf.getmembers():
            rel = m.name.lstrip("./")
            tgt = os.path.join(dst, rel)
            if m.isdir():
                os.makedirs(tgt, exist_ok=True)
                continue
            if not m.isreg():
                continue
            names.append(rel)
            try:
                os.makedirs(os.path.dirname(tgt) or dst, exist_ok=True)
                blob = tf.extractfile(m).read()
                with open(tgt, "wb") as fh:
                    fh.write(blob)
                done += 1
            except (PermissionError, OSError) as exc:
                skipped.append((rel, type(exc).__name__))

    got = [os.path.relpath(os.path.join(dp, f), dst)
           for dp, _, fs in os.walk(dst) for f in fs]
    missing = sorted(set(names) - set(got))
    print("包内文件 %d 个；已落盘 %d 个；被拒写 %d 个" % (len(names), done, len(skipped)))
    for name, err in skipped[:10]:
        print("   ⚠️ 跳过 %s（%s）" % (name, err))
    print("缺失 %d 个%s" % (len(missing), "（与被拒写一致）" if len(missing) == len(skipped) else "❗"))
    for probe in ("data/fagui_rag/criteria/标准现行性.json",
                  "data/eia_report_gen/判据库/报告表结构.json",
                  "data/eia_audit/audit/criteria.py",
                  "home/test/xishu_qingyu_serve/xishu_pipeline/retrieve.py",
                  "home/test/真机验收A档.py"):
        p = os.path.join(dst, probe)
        print("  %s %s" % ("✅" if os.path.isfile(p) else "❌", probe))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
