"""前端模块语法检查。

为什么要写成文件而不是命令行：PowerShell 对内联引号/`$(...)`/管道的解析
很坑，之前在这上面栽过 8 次。写成文件一次跑完。

为什么先复制成 .mjs：`node --check xx.js` 会按 CommonJS 解析，
遇到 `export`/`import` 直接报 "Unexpected token 'export'"。
复制成 .mjs 后 node 按 ES 模块解析，才是真的在检查我们的代码。

注意：`node --check` **不解析 import**（不检查被导入的文件存不存在、
导出名对不对），但能抓出重复声明、括号不匹配这类语法错误。
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JS_DIR = ROOT / "_中间产物" / "重构工作区" / "frontend" / "js"

FILES = ["util.js", "message.js", "store.js", "ask.js", "kg.js",
         "views.js", "image.js", "main.js"]

# 工作区内的临时目录（系统 %TEMP% 在沙箱里不可写）
tmp = ROOT / "_中间产物" / "_语法检查_tmp"
if tmp.exists():
    shutil.rmtree(tmp)
tmp.mkdir(parents=True)

fails = []
for name in FILES:
    src = JS_DIR / name
    if not src.is_file():
        fails.append((name, "文件不存在"))
        continue
    dst = tmp / (src.stem + ".mjs")
    shutil.copyfile(src, dst)
    proc = subprocess.run(["node", "--check", str(dst)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if proc.returncode == 0:
        print("  OK   %s" % name)
    else:
        err = (proc.stderr or "").strip().splitlines()
        fails.append((name, "\n".join(err[:6])))

# ---- 反向自检：检查器本身能不能抓到错误 ----
#
# 不验这一下的话，"全部 OK"可能只是因为 node --check 根本没在读文件。
# 造一个必然有语法错误的文件，必须被抓出来。
print()
print("=== 反向自检（构造语法错误，必须被抓到）===")
bad = tmp / "_故意写错.mjs"
bad.write_text("export function x( { return 1 }\n", encoding="utf-8")
proc = subprocess.run(["node", "--check", str(bad)],
                      capture_output=True, text=True, encoding="utf-8", errors="replace")
if proc.returncode != 0:
    print("  OK   检查器确实会报错（说明上面的通过是真的通过）")
else:
    fails.append(("反向自检", "构造的语法错误竟然通过了 —— 检查器没生效"))

# ---- 再验一遍：关键导出与关键改动确实在文件里 ----
print()
print("=== 关键改动落位检查 ===")
checks = [
    ("ask.js", "am.streaming = false", "生成结束后把 streaming 置假（第 1 项）"),
    ("ask.js", "function friendlyError(", "友好错误文案表（第 3 项）"),
    ("ask.js", "console.error('[悉数清宇] 请求出错'", "真实错误进控制台（第 3 项）"),
    ("message.js", "m.streaming === true", "按 streaming 决定展开/折叠（第 1 项）"),
    ("message.js", "/doc/info?source=", "先探测再加载原文（第 2 项）"),
    ("message.js", "/doc/text?source=", "文本版全文回退（第 2 项）"),
    ("message.js", "err-detail", "错误详情折叠区（第 3 项）"),
    ("message.js", "degraded-note", "降级提示条（第 4 项）"),
]
for fname, needle, desc in checks:
    text = (JS_DIR / fname).read_text(encoding="utf-8")
    if needle in text:
        print("  OK   %-28s %s" % (desc, fname))
    else:
        fails.append((fname, "缺少关键改动：" + needle))
