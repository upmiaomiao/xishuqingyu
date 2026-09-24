#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前端 DOM 引用校验：JS 里 getElementById 引用的 id 是否都真实存在于 HTML。

为什么做这个：这类"引用了不存在的元素"的错误在浏览器里表现为
「点了没反应 / 上传图片后报错」，服务端日志里一点痕迹都没有，
是纯前端的静默故障。用静态比对可以一次全查出来。

只做保守判定：把 JS 里 getElementById('X') 的 X 与 HTML 里 id="X" 求差集。

--- 2026-09-18 修订（配合前端重构阶段 2b/3）---
原版有两处会**假绿**，必须修：

① 它只跟一层 <script src>。首页的 JS 拆成 8 个 ES 模块后，只有 main.js 被取到
   （它只有 1 处 getElementById），其余 7 个模块全没看 —— 于是"引用的 id：1 个、
   没有悬空引用"，看起来全绿，实际 97% 的代码没查。这比报错更危险。
   现在递归跟随 import / import() 图，并把**扫描覆盖率**打出来。

② 它把 /gen 与 /audit 页面的 id 并进 declared，却**没有把这两个页面的模块**并进 js。
   方向反了：模块（gen_ui.js / audit_ui.js）才是引用方，页面只是 id 的声明方。
   现在两侧都按同一张页面清单来取。

③ 另外加一条自检：本次扫描到的 getElementById 引用数若少于阈值，直接判失败 ——
   宁可吵，也不要"因为没扫到所以全绿"。
"""
from __future__ import annotations

import re
import sys
import urllib.request

BASE = "http://10.201.31.10:8011"

# 自检阈值：任一低于下限就判失败，说明模块图没跟上、检查在空转。
# 为什么必须有这个：原版只跟一层 <script src>，重构后只扫到 1 处引用却报"没有悬空引用" ——
# 这种假绿比报错危险得多（报错会去看，假绿就直接放过去了）。
# 当前实测：11 个 JS 文件、65 处引用。留出余量，新增模块只会让这两个数变大。
MIN_FILES = 9
MIN_REFS = 50


def fetch(path):
    with urllib.request.urlopen(BASE + path, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def _resolve(src, ref):
    if ref.startswith("/"):
        return ref
    if ref.startswith("./"):
        ref = ref[2:]
    base = src.rsplit("/", 1)[0] if "/" in src else ""
    parts = (base + "/" + ref).split("/")
    out = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p not in ("", "."):
            out.append(p)
    return "/" + "/".join(out)


def collect_js(entry, seen, log):
    """取 entry 指向的 JS，并递归跟随它的 import 图（含动态 import()）。"""
    if entry in seen:
        return ""
    seen.add(entry)
    try:
        body = fetch(entry)
    except Exception as e:                                          # noqa: BLE001
        log.append("  ! 取不到 %s：%s" % (entry, e))
        return ""
    log.append("    %-32s %6d 字符" % (entry, len(body)))
    out = [body]
    for m in re.finditer(r"""\bfrom\s*["']([^"']+)["']|\bimport\s*\(\s*["']([^"']+)["']""", body):
        ref = m.group(1) or m.group(2)
        if ref.startswith(("./", "/")):
            out.append(collect_js(_resolve(entry, ref), seen, log))
    return "\n".join(out)


def ids_in(html):
    return set(re.findall(r"""\bid\s*=\s*["']([^"']+)["']""", html))


def refs_in(js):
    """返回 {被引用的id: 出现次数}"""
    out = {}
    for m in re.finditer(r"""getElementById\(\s*["']([^"']+)["']\s*\)""", js):
        out[m.group(1)] = out.get(m.group(1), 0) + 1
    return out


def created_in(js):
    """返回 JS 里**动态创建**的 id 集合（`el.id = 'xxx'`）。

    2026-09-18 补：原先只比对「JS 引用的 id」与「HTML 里声明的 id」，
    于是 store.js 里按需创建的 toast / rowMenu / projPicker 被当成悬空引用报了 3 个失败。
    它们其实是 `document.createElement` 之后设的 id，查找处也都有 null 保护。
    误报的代价不只是噪音 —— 习惯了"这3个是误报"之后，真悬空引用就混在里面看不见了。
    所以这里把动态创建的 id 也认出来，同时**照旧检查那些查找点有没有 null 保护**
    （见下面的"直接取属性"一节）。
    """
    return set(re.findall(r"""\.\s*id\s*=\s*["']([^"']+)["']""", js))


def unguarded_dynamic(js, excused_ids):
    """在被排除的动态 id 里，找出**引用处看不到判断**的那些。

    抽成函数是为了能在"反向用例"里复用 —— 否则这段逻辑永远没被证伪过，
    它要是写错了（比如正则永远匹配到 if），就会安安静静地放行真 bug。
    """
    out = []
    for k in excused_ids:
        for m in re.finditer(r"""getElementById\(\s*["']%s["']\s*\)""" % re.escape(k), js):
            tail = js[m.end():m.end() + 160]
            if not re.search(r"\bif\s*\(|\|\||\?\?", tail):
                out.append(k)
            break                                       # 每个 id 只看第一处，避免重复刷屏
    return out


# 站点上所有"宿主页面"：id 在这些页面里声明，模块在这些页面里被加载。
PAGES = ("/", "/gen", "/audit")


def main():
    declared, js, seen, log = set(), [], set(), []

    print("=== 逐页收集：外链 JS（含 ES 模块 import 图）与声明的 id ===")
    for page in PAGES:
        try:
            html = fetch(page)
        except Exception as e:                                      # noqa: BLE001
            print("  ! 取不到 %s：%s" % (page, e))
            continue
        n_ids = len(ids_in(html))
        declared |= ids_in(html)
        inline = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)
        inline = [s for s in inline if s.strip()]
        print("  %-8s %6d 字符 / 声明 id %2d 个 / 内联脚本 %d 段" % (page, len(html), n_ids, len(inline)))
        js.extend(inline)                                           # 内联脚本（如已无则为空）
        for src in re.findall(r"""<script[^>]+src\s*=\s*["']([^"']+)["']""", html):
            if src.startswith("http"):
                continue
            js.append(collect_js(src, seen, log))

    print()
    print("  跟随到的 JS 文件 %d 个：" % len(seen))
    for line in log:
        print(line)

    body = "\n".join(js)
    refs = refs_in(body)
    print()
    print("HTML 里声明的 id：%d 个" % len(declared))
    print("JS 里 getElementById 引用的 id：%d 个（共 %d 处）"
          % (len(refs), sum(refs.values())))

    bad = 0
    # ---- 自检：别因为没扫到而假绿
    print()
    n_refs = sum(refs.values())
    if len(seen) < MIN_FILES:
        print("★ 只跟随到 %d 个 JS 文件（下限 %d）—— 模块图没跟上，判失败" % (len(seen), MIN_FILES))
        bad += 1
    else:
        print("√ 模块图已跟随（%d 个 JS 文件 ≥ 下限 %d）" % (len(seen), MIN_FILES))
    if n_refs < MIN_REFS:
        print("★ 只扫到 %d 处引用（下限 %d）—— 检查在空转，判失败" % (n_refs, MIN_REFS))
        bad += 1
    else:
        print("√ 引用覆盖率自检通过（%d 处 ≥ 下限 %d）" % (n_refs, MIN_REFS))

    created = created_in(body)
    missing = sorted(k for k in refs if k not in declared and k not in created)
    excused = sorted(k for k in refs if k not in declared and k in created)
    print()
    if excused:
        print("· 以下是 JS 里动态创建的 id（createElement 后设 id），不算悬空：%d 个" % len(excused))
        for k in excused:
            print("    %-28s 被引用 %d 次　（查找处需有 null 保护，见下节）" % (k, refs[k]))
    if missing:
        print("★ 引用了但 HTML 里不存在、JS 里也没创建（会导致 null.xxx 抛错）：%d 个" % len(missing))
        for k in missing:
            print("    %-28s 被引用 %d 次" % (k, refs[k]))
        bad += len(missing)
    else:
        print("√ 没有悬空引用（动态创建的已排除）")

    # 把动态创建的 id 排除掉之后，必须单独确认它们**有 null 保护** ——
    # 否则"排除"就成了"放行"，比误报更糟。
    if excused:
        print()
        print("=== 动态创建的 id：查找处必须有 null 保护 ===")
        bad_ones = unguarded_dynamic(body, excused)
        for k in excused:
            if k in bad_ones:
                print("  × %-24s 引用后 160 字符内没有 if/||/?? —— 可能 null 崩溃" % k)
            else:
                print("  √ %-24s 引用点有判断" % k)
        bad += len(bad_ones)

    # 额外：找 JS 里访问 .checked / .value / .textContent 的可疑链
    print()
    print("=== 直接对 getElementById 结果取属性、且该 id 可能不存在的表达式 ===")
    pat = re.compile(r"""getElementById\(\s*["']([^"']+)["']\s*\)\s*\.\s*(\w+)""")
    seen2, n_susp = set(), 0
    for m in pat.finditer(body):
        i, attr = m.group(1), m.group(2)
        if i not in declared and (i, attr) not in seen2:
            seen2.add((i, attr))
            print("    getElementById(%r).%s" % (i, attr))
            n_susp += 1
    if not n_susp:
        print("    （无）")

    # ---- 反向用例：证明比对本身有效
    print()
    print("=== 反向用例（证明检查不是空转）===")
    fake = body + '\nconst z = document.getElementById("__NO_SUCH_ID__");\n'
    got = sorted(k for k in refs_in(fake) if k not in declared and k not in created_in(fake))
    ok_rev = "__NO_SUCH_ID__" in got
    print("  %s 注入一个不存在的 id 必须被发现" % ("√" if ok_rev else "×"))
    if not ok_rev:
        bad += 1

    # 第二条反向用例：证明"动态 id 的 null 保护"这一路不是永远通过。
    # 构造一个"创建了、但引用处没有判断"的 id，检查必须报出来。
    fake2 = (
        'const w = document.createElement("div");\n'
        'w.id = "__DYN_NOGUARD__";\n'
        'document.body.appendChild(w);\n'
        'document.getElementById("__DYN_NOGUARD__").textContent = "x";\n'
    )
    dyn2 = sorted(k for k in refs_in(fake2) if k not in declared and k in created_in(fake2))
    ung2 = unguarded_dynamic(fake2, dyn2)
    ok_rev2 = "__DYN_NOGUARD__" in ung2
    print("  %s 动态创建但无 null 保护的 id 必须被测出" % ("√" if ok_rev2 else "×"))
    if not ok_rev2:
        bad += 1

    # 第三条：有保护的不能被误报（否则这条检查会因为太吵而被无视）
    fake3 = (
        'const v = document.createElement("div");\n'
        'v.id = "__DYN_GUARDED__";\n'
        'const hit = document.getElementById("__DYN_GUARDED__");\n'
        'if (hit) hit.textContent = "x";\n'
    )
    dyn3 = sorted(k for k in refs_in(fake3) if k not in declared and k in created_in(fake3))
    ok_rev3 = "__DYN_GUARDED__" not in unguarded_dynamic(fake3, dyn3)
    print("  %s 有 null 保护的动态 id 不该被误报" % ("√" if ok_rev3 else "×"))
    if not ok_rev3:
        bad += 1

    print()
    print("=" * 62)
    print("==== %s ====" % ("通过：无悬空引用且覆盖充分" if not bad else "失败 %d 项" % bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
