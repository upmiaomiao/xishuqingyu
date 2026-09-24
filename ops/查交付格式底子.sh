#!/bin/bash
# 只读：能不能生成 Word / _cache 里存的是什么
set -u
PY=/home/test/fagui_serve/.venv/bin/python
echo "=== 有没有 docx / reportlab 之类 ==="
$PY - <<'PYEOF'
import importlib
for m in ("docx", "reportlab", "weasyprint", "markdown", "jinja2", "pymupdf", "fitz"):
    try:
        mod = importlib.import_module(m)
        print("  ok   ", m, getattr(mod, "__version__", ""))
    except Exception as exc:
        print("  MISS ", m, type(exc).__name__)
PYEOF
echo
echo "=== _cache 里一份的结构 ==="
$PY - <<'PYEOF'
import glob, json, os
fs = [f for f in glob.glob("/data/eia_audit/_cache/*.json")]
fs.sort(key=os.path.getsize)
p = fs[-1]
print("文件：", p, os.path.getsize(p), "字节")
d = json.load(open(p, encoding="utf-8"))
print("顶层键：", list(d.keys())[:20] if isinstance(d, dict) else type(d))
if isinstance(d, dict):
    for k, v in list(d.items())[:8]:
        s = json.dumps(v, ensure_ascii=False)[:200]
        print("  %-16s %s" % (k, s))
PYEOF
