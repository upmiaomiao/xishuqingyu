#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阶段 3：gen_ui.js / audit_ui.js 从「IIFE 传统脚本」转成 ES 模块。

改动清单（每条都断言生效，避免静默漏改）：
  1. 去掉 IIFE 外壳 `(function () {` … `})();`，正文整体反缩进 2 空格
  2. 去掉 'use strict'（ES 模块天生严格模式）
  3. mountGenUI / setEmbedded / mountAuditUI 加 export
  4. 去掉 window.mountGenUI / window.setGenEmbedded / window.mountAuditUI 赋值
     （消费方 views.js 与 audit.html 改为 import）
  5. gen_ui.js 里 `s == null ? "" : s` -> `s ?? ""`
     ★ 注意：不能简单改成 `=== null`！`== null` 是**故意的**，同时匹配 null 和 undefined。
       上一版我就差点改成 === null，那会让 undefined 走进 String(undefined) = "undefined"。
  6. 头部注释里的 window.* 契约描述同步改成 export 契约

输入：*.varfix.js（已做 var->const/let 且经 AST 等价验证）
输出：同名 .js（就地覆盖工作副本）
"""
from __future__ import annotations

import io
import re

W = r"_中间产物/重构工作区/xishu_pipeline/static"

SPECS = [
    {
        "name": "gen_ui.js",
        "iface_open": "(function () {",
        "iface_close": "})();",
        "exports": [("function mountGenUI(el) {", "export function mountGenUI(el) {"),
                    ("function setEmbedded(on) {", "export function setEmbedded(on) {")],
        "drop_lines": ["window.mountGenUI = mountGenUI;", "window.setGenEmbedded = setEmbedded;"],
        "text_fixes": [
            ('String(s == null ? "" : s)', 'String(s ?? "")'),
            ("暴露 window.mountGenUI(容器)，由宿主页面决定挂到哪儿。",
             "ES 模块，导出 mountGenUI(容器) 与 setEmbedded(on)，由宿主页面决定挂到哪儿。"),
            ("· 独立页靠 body.ge-standalone 自动挂载；宿主页自己调 mountGenUI。",
             "· 独立页靠 body.ge-standalone 自动挂载；宿主页 `import` 后自己调 mountGenUI。"),
        ],
    },
    {
        "name": "audit_ui.js",
        "iface_open": "(function () {",
        "iface_close": "})();",
        "exports": [("function mountAuditUI(root, opts) {", "export function mountAuditUI(root, opts) {")],
        "drop_lines": ["window.mountAuditUI = mountAuditUI;"],
        "text_fixes": [
            ("· 只暴露 window.mountAuditUI 一个入口，其余全部闭包内；",
             "· ES 模块，只导出 mountAuditUI 一个入口，其余全部模块内私有；"),
        ],
    },
]

for sp in SPECS:
    name = sp["name"]
    src_path = "%s/%s" % (W, name.replace(".js", ".varfix.js"))
    text = io.open(src_path, encoding="utf-8").read()
    before_bytes = len(text.encode())
    orig = text
    lines = text.split("\n")

    # --- 1. 定位 IIFE 外壳 ---
    opens = [i for i, l in enumerate(lines) if l.strip() == sp["iface_open"]]
    closes = [i for i, l in enumerate(lines) if l.strip() == sp["iface_close"]]
    assert len(opens) == 1, "%s：IIFE 开头找到 %d 个" % (name, len(opens))
    assert len(closes) == 1, "%s：IIFE 结尾找到 %d 个" % (name, len(closes))
    o, c = opens[0], closes[0]
    assert o < c, "%s：IIFE 位置颠倒" % name
    # 外壳必须在最外层（开头之前只有注释，结尾之后什么都没有）
    assert all(l.strip() == "" or l.strip().startswith(("/*", "*", "*/"))
               for l in lines[:o]), "%s：IIFE 之前有非注释代码" % name
    assert all(l.strip() == "" for l in lines[c + 1:]), "%s：IIFE 之后还有代码" % name

    body = lines[o + 1:c]

    # --- 2. 去掉 'use strict' ---
    strict_idx = [i for i, l in enumerate(body) if re.match(r"^\s*['\"]use strict['\"];\s*$", l)]
    assert len(strict_idx) == 1, "%s：'use strict' 找到 %d 个" % (name, len(strict_idx))
    del body[strict_idx[0]]
    # 去掉紧随其后的多余空行（原来 use strict 后面有一行空行）
    if body and body[0].strip() == "":
        del body[0]

    # --- 3. 反缩进 2 空格 ---
    de = []
    for l in body:
        if l.startswith("  "):
            de.append(l[2:])
        elif l.strip() == "":
            de.append("")
        else:
            de.append(l)   # 不该发生，留着让下面的检查暴露
    body = de

    # --- 4. 去掉 window 赋值 ---
    for dl in sp["drop_lines"]:
        hits = [i for i, l in enumerate(body) if l.strip() == dl]
        assert len(hits) == 1, "%s：找不到要删的 `%s`（找到 %d 个）" % (name, dl, len(hits))
        del body[hits[0]]
    # 清掉因删除产生的连续空行
    cleaned = []
    for l in body:
        if l.strip() == "" and cleaned and cleaned[-1].strip() == "":
            continue
        cleaned.append(l)
    body = cleaned

    text = "\n".join(lines[:o] + body + lines[c + 1:])

    # --- 5. export ---
    for old, new in sp["exports"]:
        assert text.count(old) == 1, "%s：找不到唯一声明 `%s`（%d 处）" % (name, old, text.count(old))
        text = text.replace(old, new, 1)

    # --- 6. 文本修正 ---
    for old, new in sp["text_fixes"]:
        assert text.count(old) == 1, "%s：找不到唯一片段 `%s`（%d 处）" % (name, old[:40], text.count(old))
        text = text.replace(old, new, 1)

    # --- 收尾：去掉末尾多余空行 ---
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text.endswith("\n"):
        text += "\n"

    # 头部注释补一行模块格式说明
    head_note = (" *\n * 2026-09-18 重构（阶段 3）：由 IIFE 传统脚本改为 ES 模块，\n"
                 " *   var 全部改为 const/let（AST 逐节点验证等价），\n"
                 " *   挂载入口由 window.* 改为 export。\n")
    m = re.match(r"(/\*.*?\*/)", text, re.S)
    assert m, "%s：找不到头部注释" % name
    blk = m.group(1)
    assert blk.endswith("*/")
    text = text.replace(blk, blk[:-2].rstrip() + "\n" + head_note + " */", 1)

    out_path = "%s/%s" % (W, name)
    io.open(out_path, "w", encoding="utf-8", newline="\n").write(text)

    print("%-14s %6d 字节 -> %6d 字节   %d 行" % (name, before_bytes, len(text.encode()),
                                                  text.count("\n") + 1))
    print("    IIFE 外壳：行 %d 与 %d 已去除，正文反缩进 2 空格" % (o + 1, c + 1))
    print("    export：%s" % ", ".join(new.split("(")[0].replace("export function ", "")
                                      for _old, new in sp["exports"]))
    print("    删除 window 赋值 %d 处；文本修正 %d 处" % (len(sp["drop_lines"]), len(sp["text_fixes"])))
    print("    残留 window.mount*：%d 处；残留 var：%d 处；残留 ==：%d 处"
          % (len(re.findall(r"window\.(?:mountGenUI|mountAuditUI|setGenEmbedded)", text)),
             len(re.findall(r"(?<![.\w$])var\s+[\w$]", text)),
             len(re.findall(r"[^=!<>]==[^=]", text))))
    print()
