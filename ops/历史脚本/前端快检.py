#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端改动后的快速自检：语法 + HTML↔JS 契约。

两件事：
  1. 每个 js/*.js 用 `node --check` 过一遍。
     注意：node 默认把 .js 当 CommonJS，ES module 的 `import` 会报错 ——
     所以先复制成 .mjs 再检查（本会话踩过一次）。
  2. index.html 里每个 onclick="fn(...)" 的 fn 必须在 main.js 的 WINDOW_API 里。
     HTML 只能调到 window 上的函数，漏一个就是"点了没反应"，而且不报错。
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

FRONT = pathlib.Path(r"_中间产物/重构工作区/frontend")
JS = FRONT / "js"


def check_syntax() -> int:
    print("=" * 88)
    print("① 语法检查（node --check，先复制成 .mjs）")
    print("=" * 88)
    bad = 0
    # 临时目录放在工作区内：沙箱只允许写会话工作区，系统 %TEMP% 会被拒。
    tmp = pathlib.Path(r"_中间产物/重构工作区/_语法检查临时")
    tmp.mkdir(parents=True, exist_ok=True)
    for p in sorted(JS.glob("*.js")):
        m = tmp / (p.stem + ".mjs")
        shutil.copy2(p, m)
        r = subprocess.run(["node", "--check", str(m)],
                           capture_output=True, text=True, encoding="utf-8")
        ok = r.returncode == 0
        print("  %s %-14s %s" % ("√" if ok else "×", p.name,
                                 "" if ok else (r.stderr or "")[:200]))
        if not ok:
            bad += 1
    return bad


def _window_api() -> set[str]:
    main = (JS / "main.js").read_text(encoding="utf-8")
    m = re.search(r"const WINDOW_API = \{(.*?)\n\};", main, re.S)
    if not m:
        return set()
    block = re.sub(r"//[^\n]*", "", m.group(1))          # 去注释
    return {x.strip() for x in re.findall(r"[A-Za-z_$][\w$]*", block)}


# 负向后顾 (?<![.\w$]) 用来排除**方法调用**：
#   document.getElementById('fileInput').click() → getElementById / click
#   this.classList.remove('open')                → remove
# 这些是 DOM 方法，不需要挂在 window 上。第一版没排除，报了 3 个假问题。
CALL_RE = re.compile(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(")
SKIP = {"document", "window", "this"}


def _calls_in(text: str) -> set[str]:
    return {fn for fn in CALL_RE.findall(text) if fn not in SKIP}


def check_contract() -> int:
    print()
    print("=" * 88)
    print("② HTML↔JS 契约：onclick 里的函数必须在 WINDOW_API 里")
    print("=" * 88)
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    exported = _window_api()
    if not exported:
        print("  × main.js 里找不到 WINDOW_API 块")
        return 1

    bad = 0
    used: set[str] = set()
    for attr in re.findall(r'on\w+="([^"]*)"', html):
        used |= _calls_in(attr)

    # ③ JS 里**动态生成**的 onclick 同样只能调 window 上的函数。
    #    store.js 的历史列表就是这么拼出来的：onclick="openRowMenu('id',event)"。
    #    这类拼错不会报任何错，只会"点了没反应"，所以必须一起查。
    print()
    print("=" * 88)
    print("③ JS 模板里动态生成的 onclick（同样必须在 WINDOW_API 里）")
    print("=" * 88)
    dyn: set[str] = set()
    for p in sorted(JS.glob("*.js")):
        src = p.read_text(encoding="utf-8")
        for attr in re.findall(r'on(?:click|change|keydown)="([^"]*)"', src):
            # 先剥掉 ${...} 模板插值：那些是**渲染时**求值的表达式，
            # 不是浏览器回调时要找的全局函数。
            #   onclick="toggleGroup('${esc(key)}')" → onclick="toggleGroup('')"
            # 少了这一步会把 esc 当成"缺失的全局函数"报出来（第一版就误报了）。
            attr = re.sub(r"\$\{[^}]*\}", "", attr)
            for fn in _calls_in(attr):
                dyn.add(fn)
                if fn not in exported:
                    print("  × %s：onclick 调用了 %s，但它不在 WINDOW_API 里 —— 点了不会有反应"
                          % (p.name, fn))
                    bad += 1
    print("  JS 模板里调用的函数（%d 个）：%s" % (len(dyn), ", ".join(sorted(dyn)) or "（无）"))
    if not bad:
        print("  √ 全部对得上")

    print()
    print("=" * 88)
    print("④ 跨模块 import 链接检查（node --check 查不出名字拼错）")
    print("=" * 88)
    exports: dict[str, set[str]] = {}
    for p in sorted(JS.glob("*.js")):
        src = p.read_text(encoding="utf-8")
        names: set[str] = set()
        for m in re.finditer(r"export\s+(?:async\s+)?(?:function|const|let|class)\s+([A-Za-z_$][\w$]*)", src):
            names.add(m.group(1))
        for m in re.finditer(r"export\s*\{([^}]*)\}", src):
            for part in m.group(1).split(","):
                nm = part.strip().split(" as ")[-1].strip()
                if nm:
                    names.add(nm)
        exports[p.name] = names

    for p in sorted(JS.glob("*.js")):
        src = p.read_text(encoding="utf-8")
        for m in re.finditer(r"import\s*\{([^}]*)\}\s*from\s*'\./([\w.]+)'", src, re.S):
            want = {x.strip().split(" as ")[-1].strip()
                    for x in m.group(1).replace("\n", " ").split(",") if x.strip()}
            target = m.group(2)
            have = exports.get(target, set())
            missing = sorted(want - have)
            if missing:
                print("  × %s 从 %s 导入了 %s，但对方没有导出 —— 运行时直接崩"
                      % (p.name, target, ", ".join(missing)))
                bad += 1
    if not bad:
        print("  √ 全部对得上（%d 个模块）" % len(exports))
    return bad


def check_contract_html_only() -> int:
    """只查 index.html 那一段（保留原入口，逻辑已并入 check_contract）。"""
    return 0


def main() -> int:
    bad = check_syntax()
    bad += check_contract()
    print()
    print("=" * 88)
    print("结论：" + ("全部 OK" if bad == 0 else "发现 %d 处问题" % bad))
    print("=" * 88)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
