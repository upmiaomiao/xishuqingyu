#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态检查：模块里**用了但没导入**的名字。

为什么需要它
============
`python -m py_compile` 只查语法，查不出 NameError —— 而 NameError 是运行时才发生的。
2026-09-18 那次改造就是这么翻车的：一个批量脚本重写 `from .errors import (...)` 时
把 `error_body` 写丢了，`py_compile` 全绿，上线后**每一个接口都 500**，
因为三个异常处理器都用了这个名字。

本脚本用 AST 把"模块里出现过的名字"和"真正绑定过的名字"对一遍，
专门盯住从 `.errors` 导入的那批（改动最频繁的那组）。

有意保持保守：只报**确定**没绑定的名字，不做完整的 pyflakes 数据流分析，
避免误报把真问题淹掉。
"""
from __future__ import annotations

import ast
import pathlib
import sys

W = pathlib.Path(r"_中间产物/重构工作区/xishu_pipeline")

# 只盯这几个模块（其余是机械切分产物，本轮没动）
TARGETS = ["errors.py", "routes.py", "gen_routes.py", "audit_routes.py",
           "normalize.py", "llm.py", "pipeline.py"]

# errors.py 对外提供的全部名字 —— 就是从 `.errors` 能导入的东西
ERRORS_EXPORTS = {
    "HTTP_STATUS", "STATUS_FALLBACK", "DEFAULT_MESSAGE", "PYDANTIC_MSG",
    "ApiError", "code_for_status", "new_request_id", "error_body",
    "format_validation_error",
}

BUILTINS = set(dir(__builtins__)) | {
    "self", "cls", "__name__", "__file__", "__doc__",
}


def bound_names(tree: ast.AST) -> set[str]:
    """模块里所有被**绑定**过的名字：导入、赋值、def、class、参数、for 目标、with as…"""
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.add(a.asname or a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            for a in n.names:
                out.add(a.asname or a.name)
        elif isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.add(n.name)
            if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef):
                a = n.args
                for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)):
                    out.add(arg.arg)
                if a.vararg:
                    out.add(a.vararg.arg)
                if a.kwarg:
                    out.add(a.kwarg.arg)
        elif isinstance(n, ast.Lambda):
            a = n.args
            for arg in (list(a.posonlyargs) + list(a.args) + list(a.kwonlyargs)):
                out.add(arg.arg)
            if a.vararg:
                out.add(a.vararg.arg)
            if a.kwarg:
                out.add(a.kwarg.arg)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store | ast.Del):
            out.add(n.id)
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.Global | ast.Nonlocal):
            out.update(n.names)
        elif isinstance(n, ast.comprehension) and isinstance(n.target, ast.Name):
            out.add(n.target.id)
    return out


def main() -> int:
    bad = 0
    print("=" * 92)
    print("静态检查：用了但没导入的名字")
    print("=" * 92)
    for name in TARGETS:
        p = W / name
        src = p.read_text(encoding="utf-8")
        tree = ast.parse(src)
        bound = bound_names(tree)

        imported_from_errors: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module == "errors":
                for a in n.names:
                    imported_from_errors.add(a.asname or a.name)

        used: set[str] = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}

        # 1) 本模块从 .errors 能拿到什么（用于判断"是不是该导入却漏了"）
        missing = sorted(
            x for x in used
            if x in ERRORS_EXPORTS and x not in imported_from_errors
            and x not in bound
        )
        # 2) 更一般地：用了 errors 的名字但绑定的来源不明
        actually_missing = sorted(x for x in used if x in ERRORS_EXPORTS and x not in bound)

        status = "OK" if not actually_missing else "!! 缺 %d 个" % len(actually_missing)
        print("  %-18s 从 .errors 导入 %-58s %s"
              % (name, ",".join(sorted(imported_from_errors)) or "（无）", status))
        for x in actually_missing:
            print("      ★ 用了 `%s` 但模块里没有绑定它（会 NameError —— py_compile 查不出来）" % x)
            bad += 1
    print()
    print("结论：" + ("全部 OK" if bad == 0 else "发现 %d 处" % bad))
    print("=" * 92)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
