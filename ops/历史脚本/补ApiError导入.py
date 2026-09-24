#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给 6 个模块补 `ApiError` 的导入。

迁移脚本把 raise HTTPException 换成了 raise ApiError，但导入得单独加。
这里按模块原有的相对导入风格插入（有的文件是同包 `from .errors import ...`，
routes.py 已经有一行 `from .errors import (...)`，改成往那行里加名字）。
"""
from __future__ import annotations

import pathlib
import re
import sys

W = pathlib.Path(r"_中间产物/重构工作区/xishu_pipeline")

# 文件 → (锚点行, 要插入的内容)
RULES: dict[str, tuple[str, str]] = {
    "routes.py": (
        "from .errors import (DEFAULT_MESSAGE, code_for_status, error_body,      # noqa: E402",
        "from .errors import (DEFAULT_MESSAGE, ApiError, code_for_status,       # noqa: E402",
    ),
    "gen_routes.py": (
        "from fastapi.responses import FileResponse, HTMLResponse, Response\n",
        "from fastapi.responses import FileResponse, HTMLResponse, Response\n\nfrom .errors import ApiError\n",
    ),
    "audit_routes.py": (
        "from fastapi.responses import FileResponse, HTMLResponse, Response\n",
        "from fastapi.responses import FileResponse, HTMLResponse, Response\n\nfrom .errors import ApiError\n",
    ),
    "normalize.py": (
        "from .config import DEFAULT_TOP_K, MAX_IMAGE_CHARS   # noqa: E402\n",
        "from .config import DEFAULT_TOP_K, MAX_IMAGE_CHARS   # noqa: E402\nfrom .errors import ApiError   # noqa: E402\n",
    ),
    "llm.py": (
        "from .config import MODEL_NAME, MODEL_URL   # noqa: E402\n",
        "from .config import MODEL_NAME, MODEL_URL   # noqa: E402\nfrom .errors import ApiError   # noqa: E402\n",
    ),
    "pipeline.py": (
        "from .config import MODEL_NAME\n",
        "from .config import MODEL_NAME\nfrom .errors import ApiError\n",
    ),
}


def main() -> int:
    rc = 0
    for name, (old, new) in RULES.items():
        p = W / name
        text = p.read_text(encoding="utf-8")
        # 幂等判断只看**导入**，不能只看 "ApiError" 这个词 ——
        # routes.py 的注释里本来就有"（含 ApiError）"，那样会误判成已导入。
        if re.search(r"ApiError,|import ApiError", text):
            print("  %-18s 已经有 ApiError 导入，跳过" % name)
            continue
        n = text.count(old)
        if n != 1:
            print("  %-18s !! 锚点出现 %d 次（应为 1 次），不猜，跳过" % (name, n))
            rc = 1
            continue
        p.write_text(text.replace(old, new, 1), encoding="utf-8")
        print("  %-18s 已插入 ApiError 导入" % name)
    return rc


if __name__ == "__main__":
    sys.exit(main())
