#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把「报告编制」挂进 8011 站点：① routes.py 挂 gen 路由 ② 首页侧栏加入口按钮。

为什么用脚本而不是手改/手打命令：
  · 服务器上的文件在本地没有权威副本，直接手改容易两边走偏；
  · 脚本可**重复执行**（幂等），并打印改动前后的上下文作为证据；
  · 改动前若没有备份会先备份，绝不裸改。

用法（在服务器上）：/home/test/fagui_serve/.venv/bin/python 挂载生成入口.py
"""
from __future__ import annotations

import os
import shutil
import sys
import time

SERVE = "/home/test/xishu_qingyu_serve"
ROUTES = os.path.join(SERVE, "xishu_pipeline", "routes.py")
INDEX = os.path.join(SERVE, "frontend", "index.html")
STAMP = time.strftime("%Y%m%d")

ROUTE_ANCHOR = "app.include_router(audit_router)"
ROUTE_ADD = (
    "from .gen_routes import router as gen_router   # noqa: E402\n"
    "app.include_router(gen_router)\n"
)
BTN_ANCHOR = '<button class="new-chat kg-entry" onclick="openAudit()">'
BTN_ADD = ('<button class="new-chat kg-entry" onclick="window.open(\'/gen\',\'_blank\')">'
           '\u270e&nbsp; \u62a5\u544a\u7f16\u5236</button>')


def backup(path: str, tag: str) -> str:
    b = "%s.bak_%s_%s" % (path, tag, STAMP)
    if not os.path.exists(b):
        shutil.copy2(path, b)
        print("  已备份 →", b)
    else:
        print("  备份已存在 →", b)
    return b


def patch_routes() -> bool:
    print("[1] 挂载 gen 路由：", ROUTES)
    with open(ROUTES, encoding="utf-8") as f:
        text = f.read()
    if "gen_routes" in text:
        print("  已挂载（幂等跳过）")
        return True
    if ROUTE_ANCHOR not in text:
        print("  ✗ 找不到锚点 %r，拒绝改动" % ROUTE_ANCHOR)
        return False
    backup(ROUTES, "before_gen")
    lines = text.splitlines(keepends=True)
    out, done = [], False
    for ln in lines:
        out.append(ln)
        if not done and ROUTE_ANCHOR in ln:
            out.append(ROUTE_ADD)
            done = True
    if not done:
        print("  ✗ 插入失败")
        return False
    new = "".join(out)
    with open(ROUTES, "w", encoding="utf-8", newline="\n") as f:
        f.write(new)
    print("  已插入：", ROUTE_ADD.strip().replace("\n", " / "))
    for i, ln in enumerate(new.splitlines(), 1):
        if "gen_router" in ln or "audit_router" in ln:
            print("    %4d| %s" % (i, ln))
    return True


def patch_index() -> bool:
    print("[2] 首页加入口按钮：", INDEX)
    with open(INDEX, encoding="utf-8") as f:
        text = f.read()
    if "\u62a5\u544a\u7f16\u5236" in text:
        print("  入口已存在（幂等跳过）")
        return True
    if BTN_ANCHOR not in text:
        print("  ✗ 找不到审核按钮锚点，拒绝改动")
        return False
    backup(INDEX, "before_gen_entry")
    i = text.index(BTN_ANCHOR)
    j = text.index("</button>", i) + len("</button>")
    new = text[:j] + BTN_ADD + text[j:]
    with open(INDEX, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print("  已插入按钮：", BTN_ADD)
    k = new.index(BTN_ADD)
    print("    上下文：…%s…" % new[k - 90:k + len(BTN_ADD) + 40].replace("\n", " "))
    return True


def main() -> int:
    ok1 = patch_routes()
    ok2 = patch_index()
    print("结果：routes=%s index=%s" % (ok1, ok2))
    print("提示：launcher 未改动，md5 应仍为 fdabd26175e125d4d0ca62ac4abffce1")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())