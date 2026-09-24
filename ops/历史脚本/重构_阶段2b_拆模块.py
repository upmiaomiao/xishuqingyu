#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 2b-2：把 _app_pretty.js 拆成 ES 模块。

设计（依赖图无环，靠 import 方向保证）：
    util.js     状态 + 工具 + current()            ← 无依赖
    message.js  消息渲染 / 引用 / 侧栏开关          ← util
    image.js    图片上传与压缩                      ← 无
    kg.js       知识图谱（自成一体的 canvas 逻辑）    ← util
    views.js    视图切换 + 子模块按需挂载            ← message, kg
    store.js    会话存取 / 历史 / render()          ← util, message, views
    ask.js      提问与流式                          ← util, store, message, image
    main.js     入口：绑事件、暴露 window、初始化      ← 全部

两处刻意的结构性改动（都不改可观测行为）：
  1. chats / activeId 收进 state 对象 —— ES 模块**不能给 import 进来的绑定赋值**，
     而这两个变量被 store/ask/message 多处赋值。
  2. 丢掉原来那段 monkey-patch IIFE（原 120-137 行）—— 它包 window.openAudit /
     openKnowledgeGraph / newConversation 去先 closeGen()。改成在 main.js 里
     显式包装，等价但可读。
"""
from __future__ import annotations

import io
import os
import re

SRC = r"_中间产物/重构工作区/frontend/_app_pretty.js"
OUT = r"_中间产物/重构工作区/frontend/js"

lines = io.open(SRC, encoding="utf-8").read().split("\n")
CLOSE = re.compile(r"^[}\])]")


def is_start(l: str) -> bool:
    return bool(l) and not l[0].isspace() and not CLOSE.match(l)


starts = [i for i, l in enumerate(lines) if is_start(l)]
items = {}
for k, s in enumerate(starts):
    e = (starts[k + 1] - 1) if k + 1 < len(starts) else len(lines) - 1
    items[s + 1] = "\n".join(lines[s:e + 1])

MODULES: dict[str, list[int]] = {
    "util.js":    [1, 2, 5, 10, 482],
    "message.js": [518, 521, 577, 580, 602, 618, 629, 642, 645],
    "image.js":   [763, 764, 765, 767, 771, 779, 787, 800, 832],
    "kg.js":      [13, 29, 164, 181, 201, 329, 368, 372, 375, 388, 397, 398,
                   407, 425, 433, 434, 435, 449, 452],
    "views.js":   [36, 47, 54, 66, 72, 73, 89, 95, 119, 138, 140],
    "store.js":   [456, 467, 485, 496, 502, 510, 625],
    "ask.js":     [638, 648],
    "main.js":    [840, 841, 845, 851],
}
DROPPED = [120]   # monkey-patch IIFE，改由 main.js 显式包装

IMPORTS: dict[str, list[tuple[str, list[str]]]] = {
    "util.js":    [],
    "message.js": [("util.js", ["esc", "current"])],
    "image.js":   [],
    "kg.js":      [("util.js", ["esc"])],
    "views.js":   [("message.js", ["closeSidebar", "renderMessages"]),
                   ("kg.js", ["loadKnowledgeGraphStats", "searchKnowledgeGraph"])],
    "store.js":   [("util.js", ["state", "esc", "uid", "current", "STORE"]),
                   ("message.js", ["renderMessages", "closeSidebar"]),
                   ("views.js", ["closeKnowledgeGraph"])],
    "ask.js":     [("util.js", ["state", "current"]),
                   ("store.js", ["save", "render"]),
                   ("message.js", ["renderMessages"]),
                   ("image.js", ["pendingImage", "clearPendingImage"])],
    "main.js":    [("store.js", ["load", "newConversation", "selectChat", "deleteChat"]),
                   ("message.js", ["toggleSidebar", "showCitation"]),
                   ("ask.js", ["ask", "useExample"]),
                   ("image.js", ["clearPendingImage", "onPickImage", "openImage"]),
                   ("kg.js", ["searchKnowledgeGraph"]),
                   ("views.js", ["openKnowledgeGraph", "openAudit", "openGen",
                                 "closeKnowledgeGraph", "closeGen"])],
}

HEADERS = {
    "util.js": "共享状态与工具函数。所有模块都从这里取，所以它不能反过来依赖任何模块。",
    "message.js": "消息与引用渲染、侧栏开关。纯渲染，不发起请求。",
    "image.js": "图片上传：客户端压缩成 data URL，随问题一起 POST。",
    "kg.js": "知识图谱：canvas 力导向布局、平移缩放、节点选中。自成一体。",
    "views.js": "视图切换（问答 / 图谱 / 审核 / 编制）与两个子模块的**按需加载**。",
    "store.js": "会话存取（localStorage）、历史列表、总渲染。",
    "ask.js": "提问与流式接收（SSE）。",
    "main.js": "入口：绑定事件、把需要在 HTML 里 onclick 调用的函数暴露到 window、初始化。",
}

# ---- 1. 取条目文本 ----
mod_text: dict[str, str] = {}
for mod, ls in MODULES.items():
    missing = [s for s in ls if s not in items]
    assert not missing, "%s 引用了不存在的条目 %s" % (mod, missing)
    mod_text[mod] = "\n".join(items[s] for s in ls)

# ---- 2. 状态改造 ----
SENT = "@@STATE_DECL@@"
# util.js 的 let 声明整条换掉
old_decl = mod_text["util.js"]
assert "let chats = []," in old_decl
mod_text["util.js"] = old_decl.replace(
    "let chats = [],\n  activeId = '',\n  busy = false;",
    SENT, 1)
assert SENT in mod_text["util.js"], "状态声明替换失败"

# 所有模块里 chats / activeId -> state.xxx（独立标识符，前面不是 . 或字母）
for mod in mod_text:
    t = mod_text[mod]
    t = re.sub(r"(?<![.\w$])chats(?![\w$])", "state.chats", t)
    t = re.sub(r"(?<![.\w$])activeId(?![\w$])", "state.activeId", t)
    mod_text[mod] = t

mod_text["util.js"] = mod_text["util.js"].replace(
    SENT, "export const state = { chats: [], activeId: '' };", 1)

# ask.js 自带 busy（全文件只有 ask 用它，收成模块私有）
mod_text["ask.js"] = "let busy = false; // 防重复提交；只有本模块用\n" + mod_text["ask.js"]

# ---- 3. 加 export ----
need_export: dict[str, set[str]] = {m: set() for m in MODULES}
for mod, deps in IMPORTS.items():
    for src_mod, names in deps:
        need_export[src_mod].update(names)

for mod, names in need_export.items():
    t = mod_text[mod]
    for n in sorted(names, key=len, reverse=True):
        if re.search(r"^export\s+(?:async\s+)?function\s+" + re.escape(n) + r"\b", t, re.M):
            continue
        if re.search(r"^export\s+(?:const|let)\s+" + re.escape(n) + r"\b", t, re.M):
            continue
        # function / async function
        new_t, cnt = re.subn(
            r"^(async\s+)?function\s+" + re.escape(n) + r"\b",
            lambda mm: "export %sfunction %s" % (mm.group(1) or "", n),
            t, count=1, flags=re.M)
        if cnt:
            t = new_t
            continue
        # const / let 单声明
        new_t, cnt = re.subn(
            r"^(const|let)\s+" + re.escape(n) + r"\b",
            lambda mm: "export %s %s" % (mm.group(1), n),
            t, count=1, flags=re.M)
        if cnt:
            t = new_t
            continue
        raise SystemExit("找不到 %s 里 %s 的声明，无法加 export" % (mod, n))
    mod_text[mod] = t

# ---- 4. 组装文件 ----
os.makedirs(OUT, exist_ok=True)
BANNER = "/* ============================================================\n *  %s\n * ============================================================ */\n"

for mod in MODULES:
    parts = []
    parts.append("/* 悉数清宇 · 问答主页脚本模块：%s\n *\n * %s\n *\n * 2026-09-18 从 index.html 的内联 <script> 拆出（阶段 2b）。\n * 拆分原因：Google JavaScript Style Guide —— 源文件应为 ES module；\n *   ESLint max-lines 默认 300 行。原内联脚本 125 行里塞了 42 个函数、最长行 2623 字符。\n */\n"
                 % (mod, HEADERS[mod]))
    deps = IMPORTS[mod]
    if deps:
        for src_mod, names in deps:
            parts.append("import { %s } from './%s';" % (", ".join(names), src_mod))
        parts.append("")
    parts.append(BANNER % mod)
    parts.append("")
    parts.append(mod_text[mod])
    if mod == "main.js":
        parts.append("""

/* ============================================================
 *  暴露到 window —— HTML 里的 onclick="..." 只能调到全局函数。
 *  这一份清单就是 HTML 与 JS 之间的**全部契约**，改 HTML 时对照这里。
 * ============================================================ */
const WINDOW_API = {
  // 侧栏与视图切换
  newConversation, selectChat, deleteChat, toggleSidebar,
  openKnowledgeGraph, closeKnowledgeGraph, openAudit, openGen,
  // 图谱
  searchKnowledgeGraph,
  // 提问
  ask, useExample,
  // 消息内交互
  showCitation, openImage,
  // 图片
  onPickImage, clearPendingImage,
};
Object.assign(window, WINDOW_API);

/* 切到别的视图时先收起报告编制，避免叠着。
   原代码用一段 IIFE 猴补 window.openAudit / openKnowledgeGraph / newConversation，
   这里改成显式包装 —— 等价，但不用先挂到 window 再改 window。 */
const _openAudit = openAudit,
  _openKnowledgeGraph = openKnowledgeGraph,
  _newConversation = newConversation;
window.openAudit = () => {
  closeGen();
  _openAudit();
};
window.openKnowledgeGraph = () => {
  closeGen();
  _openKnowledgeGraph();
};
window.newConversation = () => {
  closeGen();
  _newConversation();
};
""")
    text = "\n".join(parts)
    if not text.endswith("\n"):
        text += "\n"
    io.open(os.path.join(OUT, mod), "w", encoding="utf-8", newline="\n").write(text)
    print("  %-12s %4d 行  %6d 字节" % (mod, text.count("\n") + 1, len(text.encode())))

print()
print("丢弃的条目：%s（IIFE，已由 main.js 显式包装替代）" % DROPPED)
print("输出目录：%s" % OUT)
