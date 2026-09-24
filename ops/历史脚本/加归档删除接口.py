#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 gen_routes.py 追加「归档 / 彻底删除」两个接口（追加式，不动已有代码）。

为什么用脚本而不是编辑器：这个文件末尾没有换行，逐字替换匹配不稳。
本脚本只做一件事 —— 在文件末尾追加一段，追加前先确认没有重复定义。
"""
from __future__ import annotations

import ast
import io

P = r"_中间产物/线上源码/gen_routes.py"
src = io.open(P, encoding="utf-8").read()

if "/api/archive" in src or "/api/delete" in src:
    raise SystemExit("文件里已经有 archive/delete，停手不改")

APPEND = '''

def _resolve_output(name: str) -> str:
    """把前端传来的名字收敛成 OUT_DIR 下的一个真实文件。

    `os.path.basename` 挡目录穿越（`../../x.docx` → `x.docx`）；
    再要求后缀是 .docx 且确实存在，避免误删同目录下的模板等文件。
    """
    base = os.path.basename(name or "")
    if not base or not base.endswith(".docx"):
        raise HTTPException(400, "文件名不合法")
    p = os.path.join(OUT_DIR, base)
    if not os.path.isfile(p):
        raise HTTPException(404, "没有这个文件")
    return p


@router.post("/api/archive")
async def api_archive(request: Request) -> dict:
    """把一份草稿移进 _已归档/ —— **可恢复**，符合项目「归档不删除」纪律。

    只移动、不删除，是历史报告里「归档」按钮的后端。
    """
    body = await request.json()
    src = _resolve_output(body.get("name"))
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    dst = os.path.join(ARCHIVE_DIR, os.path.basename(src))
    if os.path.exists(dst):        # 同名不覆盖：加时间戳，宁可多留一份也不覆盖旧的
        stem, ext = os.path.splitext(os.path.basename(src))
        dst = os.path.join(ARCHIVE_DIR, "%s-%d%s" % (stem, int(time.time()), ext))
    shutil.move(src, dst)
    return {"ok": True, "归档到": dst, "可恢复": True}


@router.post("/api/delete")
async def api_delete(request: Request) -> dict:
    """**彻底删除**一份草稿 —— 不可恢复，前端二次确认后才调这里。"""
    body = await request.json()
    src = _resolve_output(body.get("name"))
    size = os.path.getsize(src)
    os.remove(src)
    return {"ok": True, "已删除": os.path.basename(src), "释放字节": size, "可恢复": False}
'''

new = src.rstrip("\n") + "\n" + APPEND
ast.parse(new)                     # 语法不过就不写
io.open(P, "w", encoding="utf-8", newline="\n").write(new)

print("追加完成。行数 %d → %d" % (src.count("\n") + 1, new.count("\n") + 1))
print()
print("=== 新增部分 ===")
print(APPEND)
print("=== 语法检查：通过 ===")
