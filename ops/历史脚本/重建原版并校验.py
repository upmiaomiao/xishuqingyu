#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""备份失败后的补救：确认原版是否可重建，并校验。

已知服务器上被覆盖前的三个原版 md5（备份脚本失败时那条 md5sum 打出来的）：
    c7f10340fd47f4472493a184303af23c  gen_routes.py
    5e230f5572cae1094d906cc63deae070  static/gen_ui.js
    c66be3732661d7ef51f8431940aa06f1  static/gen_ui.css

gen_ui.js / gen_ui.css：改前我另存过一份到 _中间产物/线上UI/，直接比对 md5 即可。
gen_routes.py：没有另存，但改动只有三处（import shutil / ARCHIVE_DIR / 末尾追加），
               逐条反向还原后若 md5 命中，就证明重建的是**逐字节原版**。
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil

WANT = {
    "gen_routes.py": "c7f10340fd47f4472493a184303af23c",
    "gen_ui.js": "5e230f5572cae1094d906cc63deae070",
    "gen_ui.css": "c66be3732661d7ef51f8431940aa06f1",
}


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


print("=" * 74)
print("第一步：gen_ui.js / gen_ui.css —— 用改前另存的那份比对")
print("=" * 74)
for name in ("gen_ui.js", "gen_ui.css"):
    p = os.path.join("_中间产物", "线上UI", name)
    b = io.open(p, "rb").read()
    got = md5(b)
    ok = got == WANT[name]
    print("  %-12s %s  %s" % (name, got, "★ 与原版一致" if ok else "✗ 不一致（%s）" % WANT[name]))
    if ok:
        dst = os.path.join("_中间产物", "线上源码", name + ".原版")
        shutil.copyfile(p, dst)
        print("               已另存为 %s" % dst)

print()
print("=" * 74)
print("第二步：gen_routes.py —— 反向还原三处改动")
print("=" * 74)
src = io.open(os.path.join("_中间产物", "线上源码", "gen_routes.py"), encoding="utf-8").read()

# 反向 1：去掉 import shutil
src = src.replace("import os\nimport shutil\nimport sys\n", "import os\nimport sys\n", 1)
# 反向 2：去掉 ARCHIVE_DIR
src = src.replace(
    'OUT_DIR = os.path.join(GEN_HOME, "_生成结果")\n'
    'ARCHIVE_DIR = os.path.join(OUT_DIR, "_已归档")     # 归档目录：放在 OUT_DIR 下，列表只扫 *.docx 所以不会显示出来\n',
    'OUT_DIR = os.path.join(GEN_HOME, "_生成结果")\n', 1)
# 反向 3：砍掉末尾追加的那一段
cut = src.find("\n\ndef _resolve_output(")
if cut > 0:
    src = src[:cut] + "\n"

got = md5(src.encode("utf-8"))
print("  重建结果 md5：%s" % got)
print("  服务器原版 md5：%s" % WANT["gen_routes.py"])
if got == WANT["gen_routes.py"]:
    print("  ★ 命中 —— 重建的就是逐字节原版")
    dst = os.path.join("_中间产物", "线上源码", "gen_routes.py.原版")
    io.open(dst, "w", encoding="utf-8", newline="\n").write(src)
    print("  已另存为 %s" % dst)
else:
    print("  ✗ 未命中，重建不可信，**不要**当作备份使用")
    print("  行数 %d，尾部：%r" % (src.count("\n") + 1, src[-80:]))
