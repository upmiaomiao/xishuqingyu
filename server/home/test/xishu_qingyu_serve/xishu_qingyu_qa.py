"""悉数清宇法规问答网页与 FastAPI 服务，监听 8011（薄入口）。

职责仅三件：把 app 暴露出来、把 __main__ 启动逻辑留下、把 sys.path 设好。
所有业务逻辑在 xishu_pipeline/ 包里。
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from xishu_pipeline.routes import app   # noqa: E402,F401


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.environ.get("QA_HOST", "127.0.0.1"),
        port=int(os.environ.get("QA_PORT", "8011")),
    )
