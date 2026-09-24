#!/bin/bash
D=/home/test/xishu_qingyu_serve
echo "=== 进程 ==="
ss -ltnp 2>/dev/null | grep ':8011' | sed 's/^/  /'

echo
echo "=== 线上文件 md5（应与本地一致）==="
for f in frontend/index.html frontend/audit.html frontend/gen.html \
         xishu_pipeline/static/audit_page.css xishu_pipeline/static/audit_page.js \
         xishu_pipeline/static/gen_ui.js xishu_pipeline/static/audit_ui.js \
         frontend/js/views.js frontend/js/main.js frontend/app.css; do
  if [ -f "$D/$f" ]; then
    printf '  %s  %8d  %s\n' "$(md5sum "$D/$f" | cut -d' ' -f1)" "$(stat -c%s "$D/$f")" "$f"
  else
    printf '  %-34s 缺失\n' "$f"
  fi
done

echo
echo "=== 首页结构 ==="
echo "  字节：$(stat -c%s "$D/frontend/index.html")"
echo -n "  内联 <style>/<script>："
grep -c '<style' "$D/frontend/index.html" | tr '\n' ' '
grep -c '<script[^>]*>[^<]' "$D/frontend/index.html" || true
echo "  外链："
grep -o '<link[^>]*>\|<script[^>]*>' "$D/frontend/index.html" | sed 's/^/    /'

echo
echo "=== frontend/ 与 frontend/js/ ==="
ls -l "$D/frontend/" | tail -n +2 | awk '{printf "  %7s  %s\n",$5,$9}'
echo "  ---"
ls -l "$D/frontend/js/" | tail -n +2 | awk '{printf "  %7s  %s\n",$5,$9}'

echo
echo "=== 静态资源 HTTP 抽查 ==="
for u in / /static/app.css /static/js/main.js /static/js/views.js /gen /audit \
         /gen/static/gen_ui.js /audit/static/audit_ui.js /audit/static/audit_page.js \
         /static/nope.css /static/../routes.py; do
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 5 "http://127.0.0.1:8011$u")
  printf '  %-32s %s\n' "$u" "$code"
done
