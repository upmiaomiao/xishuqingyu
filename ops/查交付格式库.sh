#!/bin/bash
# 只读：交付件格式的家底（写到哪个库有、哪个没有）
set -u
PY=/home/test/fagui_serve/.venv/bin/python
$PY - <<'PYEOF'
import importlib
mods = ["docx", "openpyxl", "xlsxwriter", "pandas", "pymupdf", "fitz",
        "reportlab", "weasyprint", "markdown", "jinja2", "PIL", "lxml"]
for m in mods:
    try:
        mod = importlib.import_module(m)
        print("  ok    %-12s %s" % (m, getattr(mod, "__version__", "")))
    except Exception as exc:
        print("  MISS  %-12s %s" % (m, type(exc).__name__))
print()
import pymupdf
d = pymupdf.open("/data/eia_reports/1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.pdf")
p = d[0]
print("pymupdf 批注能力自检（第 1 页）：")
for api in ("add_highlight_annot", "add_text_annot", "add_strikeout_annot",
            "add_freetext_annot", "add_underline_annot", "search_for", "get_text"):
    print("   %-22s %s" % (api, hasattr(p, api)))
print("   页面尺寸:", p.rect)
hits = p.search_for("环境影响报告书")
print("   search_for('环境影响报告书') →", len(hits), "处命中")
d.close()
PYEOF
