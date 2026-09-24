#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前后端语法总检：Python 用 ast，JS 复制成 .mjs 再 node --check。

为什么 JS 要先改扩展名：node --check 对 .js 按 CommonJS 解析，
遇到 `import`/`export` 直接报错 —— 那不是代码有问题，是检查方式不对。

注意：node --check **只查语法**，不解析 import。所以"语法过了"
不等于"能跑"，后面还有别的检查。
"""
import ast
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "_脚本代码" \
    else os.path.abspath(".")
if not os.path.isdir(os.path.join(ROOT, "_中间产物")):
    ROOT = os.path.abspath(".")

WS = os.path.join(ROOT, "_中间产物", "重构工作区")
TMP = os.path.join(ROOT, "_中间产物", "_语法检查_tmp")

ok = 0
bad = []


def say(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


say("=== Python 语法（ast.parse）===")
py_files = []
for base in (os.path.join(WS, "xishu_pipeline"),):
    for dirpath, dirnames, names in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for n in names:
            if n.endswith(".py"):
                py_files.append(os.path.join(dirpath, n))
for p in sorted(py_files):
    rel = os.path.relpath(p, WS)
    try:
        ast.parse(open(p, encoding="utf-8").read(), filename=p)
        say("  OK   %s" % rel)
        ok += 1
    except SyntaxError as e:
        say("  ★ 语法错 %s: 第 %s 行 %s" % (rel, e.lineno, e.msg))
        bad.append(rel)

say("")
say("=== JavaScript 语法（node --check，先复制成 .mjs）===")
if os.path.isdir(TMP):
    shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP, exist_ok=True)
js_files = []
for base in (os.path.join(WS, "frontend"), os.path.join(WS, "xishu_pipeline", "static")):
    if not os.path.isdir(base):
        continue
    for dirpath, dirnames, names in os.walk(base):
        for n in names:
            if n.endswith(".js") and not n.startswith("_"):
                js_files.append(os.path.join(dirpath, n))
for p in sorted(js_files):
    rel = os.path.relpath(p, WS)
    tmp = os.path.join(TMP, os.path.basename(p).replace(".js", "") + "_chk.mjs")
    shutil.copyfile(p, tmp)
    r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
    if r.returncode == 0:
        say("  OK   %s" % rel)
        ok += 1
    else:
        msg = (r.stderr or r.stdout).strip().splitlines()
        say("  ★ 语法错 %s" % rel)
        for line in msg[:6]:
            say("        " + line)
        bad.append(rel)

say("")
say("=== 前端 HTML 引用 vs 实际文件 ===")
import re
for page in ("index.html", "audit.html", "gen.html"):
    p = os.path.join(WS, "frontend", page)
    if not os.path.isfile(p):
        say("  ★ 缺 %s" % page)
        bad.append(page)
        continue
    html = open(p, encoding="utf-8").read()
    refs = re.findall(r'(?:src|href)="(/static/[^"]+|/audit/static/[^"]+|/gen/static/[^"]+)"', html)
    say("  %s 引用 %d 个静态资源" % (page, len(refs)))
    for r in refs:
        say("      %s" % r)
    ok += 1

say("")
say("=== 线上页面引用的静态文件在磁盘上存在吗 ===")
STATIC_ROOTS = {
    "/static/": os.path.join(WS, "frontend"),
    "/audit/static/": os.path.join(WS, "xishu_pipeline", "static"),
    "/gen/static/": os.path.join(WS, "xishu_pipeline", "static"),
}
missing = 0
for page in ("index.html", "audit.html", "gen.html"):
    p = os.path.join(WS, "frontend", page)
    if not os.path.isfile(p):
        continue
    html = open(p, encoding="utf-8").read()
    for r in re.findall(r'(?:src|href)="(/[^"]+\.(?:js|css))"', html):
        hit = None
        for prefix, root in STATIC_ROOTS.items():
            if r.startswith(prefix):
                hit = os.path.join(root, r[len(prefix):])
                break
        if hit and not os.path.isfile(hit):
            say("  ★ %s 引用了不存在的 %s" % (page, r))
            missing += 1
if missing == 0:
    say("  全部存在")
else:
    bad.append("静态引用缺失 %d 个" % missing)

say("")
say("=== kg.js / audit_ui.js 新增符号是否都在 ===")
NEW = [
    (os.path.join(WS, "frontend", "js", "kg.js"), [
        "loadKgSuggestions", "initKgSuggest",
        "hideKgSuggest", "renderKgSuggest", "chipHtml", "onKgSuggestClick",
    ]),
    (os.path.join(WS, "frontend", "js", "views.js"), [
        "loadKgSuggestions",
    ]),
    (os.path.join(WS, "frontend", "js", "main.js"), [
        "initKgSuggest",
    ]),
    (os.path.join(WS, "xishu_pipeline", "static", "audit_ui.js"), [
        "pickFile", "uploadFile", "XMLHttpRequest", "auUpload", "auFile",
    ]),
    (os.path.join(WS, "xishu_pipeline", "audit_routes.py"), [
        "_safe_pdf_name", "_unique_path", "_sha1_of", "api_upload",
        "MAX_UPLOAD_BYTES", "UploadFile",
    ]),
    (os.path.join(WS, "xishu_pipeline", "kg.py"), [
        "def graph_suggestions",
    ]),
]
for path, names in NEW:
    rel = os.path.relpath(path, WS)
    if not os.path.isfile(path):
        say("  ★ 缺文件 %s" % rel)
        bad.append(rel)
        continue
    src = open(path, encoding="utf-8").read()
    miss = [n for n in names if n not in src]
    if miss:
        say("  ★ %s 里找不到：%s" % (rel, ", ".join(miss)))
        bad.append(rel)
    else:
        say("  OK   %s （%d 个符号齐全）" % (rel, len(names)))
        ok += 1

shutil.rmtree(TMP, ignore_errors=True)

say("")
say("==== 通过 %d / 失败 %d ====" % (ok, len(bad)))
if bad:
    for b in bad:
        say("  失败：" + b)
    sys.exit(1)
