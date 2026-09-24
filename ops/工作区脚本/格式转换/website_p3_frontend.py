#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P3-1：把内嵌在 routes.py `index()` 里的整页 HTML 原样搬成 frontend/index.html。

原则仍然是「搬运，不重写」：直接取 AST 里那个字符串常量的值写文件，
再把 index() 换成读文件的实现。用法：python website_p3_frontend.py <站点目录>
"""
from __future__ import annotations

import ast
import os
import sys

SITE = sys.argv[1] if len(sys.argv) > 1 else r"D:\项目\中节能\0911训练\服务器会话\xishu_site"
PKG = os.path.join(SITE, "xishu_pipeline")
ROUTES = os.path.join(PKG, "routes.py")
FRONTEND_DIR = os.path.join(SITE, "frontend")
FRONTEND = os.path.join(FRONTEND_DIR, "index.html")

src = open(ROUTES, encoding="utf-8").read()
lines = "".join(src).splitlines(keepends=True)
tree = ast.parse(src)

fn = next(n for n in tree.body
          if isinstance(n, ast.AsyncFunctionDef) and n.name == "index")
start = min([fn.lineno] + [d.lineno for d in fn.decorator_list])
end = fn.end_lineno

# 取出被 return 的那个字符串常量
ret = next(n for n in ast.walk(fn) if isinstance(n, ast.Return))
html = ret.value.value
assert isinstance(html, str) and "<!doctype html>" in html.lower(), "没取到页面 HTML"
assert 'id="fileInput"' in html and "md-table" in html, "取到的 HTML 不完整"

os.makedirs(FRONTEND_DIR, exist_ok=True)
open(FRONTEND, "w", encoding="utf-8", newline="\n").write(html)

new_index = '''_FRONTEND_CACHE: dict[str, Any] = {}


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """首页：前端已外置到 frontend/index.html（按修改时间缓存，改完刷新即可生效）。"""
    try:
        mtime = FRONTEND_PATH.stat().st_mtime
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"前端文件缺失：{FRONTEND_PATH}") from exc
    if _FRONTEND_CACHE.get("mtime") != mtime or "html" not in _FRONTEND_CACHE:
        _FRONTEND_CACHE["html"] = FRONTEND_PATH.read_text(encoding="utf-8")
        _FRONTEND_CACHE["mtime"] = mtime
    return _FRONTEND_CACHE["html"]
'''

out = lines[:start - 1] + [new_index] + lines[end:]
text = "".join(out)
# 补 FRONTEND_PATH 的同包导入
if "FRONTEND_PATH" not in text.split("_FRONTEND_CACHE")[0]:
    text = text.replace("# ---- 同包依赖 ----\n",
                        "# ---- 同包依赖 ----\nfrom .config import FRONTEND_PATH   # noqa: E402\n", 1)
open(ROUTES, "w", encoding="utf-8", newline="\n").write(text)

print(f"前端已外置：{FRONTEND}（{len(html)} 字符，{html.count(chr(10)) + 1} 行）")
print(f"routes.py：{len(lines)} 行 → {len(text.splitlines())} 行")
