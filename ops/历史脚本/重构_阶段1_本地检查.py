#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 1 本地检查：routes.py 语法 + 改动点是否都在。"""
import io
import py_compile
import sys

P = r"_中间产物/重构工作区/xishu_pipeline/routes.py"
try:
    py_compile.compile(P, doraise=True, cfile=r"_中间产物/重构工作区/_chk.pyc")
    print("语法检查：通过")
except py_compile.PyCompileError as exc:
    print("语法错误：")
    print(exc)
    sys.exit(1)

s = io.open(P, encoding="utf-8").read()
checks = [
    ("导入 Response", "Response," in s),
    ("导入块完整", "from fastapi.responses import (FileResponse, HTMLResponse, Response," in s),
    ("新增 /static/{fname} 路由", '@app.get("/static/{fname}")' in s),
    ("FRONTEND_DIR 定义", "FRONTEND_DIR = FRONTEND_PATH.parent" in s),
    ("白名单含 app.css", '"app.css": "text/css; charset=utf-8"' in s),
    ("白名单含 app.js", '"app.js": "application/javascript; charset=utf-8"' in s),
    ("no-cache 头", '"Cache-Control": "no-cache"' in s),
    ("原有 index() 仍在", 'async def index() -> str:' in s),
    ("原有 _FRONTEND_CACHE 仍在", "_FRONTEND_CACHE: dict[str, Any] = {}" in s),
]
for name, ok in checks:
    print("  %-26s %s" % (name, "√" if ok else "✗ 缺失"))
print("行数：%d" % (s.count("\n") + 1))
if not all(ok for _n, ok in checks):
    sys.exit(1)
