#!/bin/bash
# 探底：网页预览交付件这件事，服务器上有什么可用的家伙
echo '--- 文档转换工具 ---'
for c in soffice libreoffice unoconv pandoc abiword lowriter; do
  p=$(command -v "$c")
  printf '%-12s %s\n' "$c" "${p:-无}"
done
echo '--- 无头浏览器（服务端渲染用）---'
for c in chromium chromium-browser google-chrome firefox wkhtmltopdf; do
  p=$(command -v "$c")
  printf '%-18s %s\n' "$c" "${p:-无}"
done
echo '--- venv 里的库 ---'
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import importlib.util as u
for m in ['docx', 'pymupdf', 'reportlab', 'weasyprint', 'mammoth', 'markdown', 'lxml', 'jinja2', 'PIL']:
    print('%-12s %s' % (m, bool(u.find_spec(m))))
PY
echo '--- 站点现有下载/内联响应 ---'
grep -n 'Content-Disposition\|FileResponse\|media_type' /home/test/xishu_qingyu_serve/xishu_pipeline/audit_routes.py | head -20
echo '--- frontend/audit.html 里有没有 iframe/弹层 ---'
grep -c 'iframe' /home/test/xishu_qingyu_serve/frontend/audit.html
