#!/bin/bash
# 两项改造（审核上传 + 图谱推荐词）—— 收尾核对。
set -u
S=/home/test/xishu_qingyu_serve

echo "=== 1. 线上文件指纹（本次改动的 11 个）==="
for f in \
  xishu_pipeline/kg.py xishu_pipeline/routes.py xishu_pipeline/errors.py \
  xishu_pipeline/audit_routes.py xishu_pipeline/resilience.py \
  xishu_pipeline/static/audit_ui.js \
  frontend/index.html frontend/app.css \
  frontend/js/kg.js frontend/js/views.js frontend/js/main.js \
  ; do
  if [ -f "$S/$f" ]; then
    printf '  %-38s %8d B  %s\n' "$f" "$(stat -c%s "$S/$f")" "$(md5sum "$S/$f" | cut -c1-16)"
  else
    printf '  %-38s ★ 缺失\n' "$f"
  fi
done

echo
echo "=== 2. 关键代码标记 ==="
printf '  %-40s %s\n' "audit_routes.py 有 /api/upload"   "$(grep -c '"/api/upload"' $S/xishu_pipeline/audit_routes.py)"
printf '  %-40s %s\n' "audit_routes.py 有 _safe_pdf_name" "$(grep -c '_safe_pdf_name' $S/xishu_pipeline/audit_routes.py)"
printf '  %-40s %s\n' "audit_routes.py 有 _unique_path"   "$(grep -c '_unique_path' $S/xishu_pipeline/audit_routes.py)"
printf '  %-40s %s\n' "kg.py 有 graph_suggestions"         "$(grep -c 'def graph_suggestions' $S/xishu_pipeline/kg.py)"
printf '  %-40s %s\n' "kg.py 有 _suggest_display_name"     "$(grep -c 'def _suggest_display_name' $S/xishu_pipeline/kg.py)"
printf '  %-40s %s\n' "routes.py 有 /kg/suggest"           "$(grep -c '"/kg/suggest"' $S/xishu_pipeline/routes.py)"
printf '  %-40s %s\n' "errors.py 有 E_FILE_TOO_LARGE"      "$(grep -c 'E_FILE_TOO_LARGE' $S/xishu_pipeline/errors.py)"
printf '  %-40s %s\n' "resilience.py 的 _PUNCT 是单引号 raw" "$(grep -c "_PUNCT = re.compile(r'" $S/xishu_pipeline/resilience.py)"
printf '  %-40s %s\n' "audit_ui.js 有上传按钮"             "$(grep -c 'auUpload' $S/xishu_pipeline/static/audit_ui.js)"
printf '  %-40s %s\n' "kg.js 有轮转取词"                   "$(grep -c '跨类型\*\*轮转\*\*取' $S/frontend/js/kg.js)"
printf '  %-40s %s\n' "index.html 有 kgSuggest"            "$(grep -c 'id="kgSuggest"' $S/frontend/index.html)"

echo
echo "=== 3. 服务状态 ==="
echo "  pid = $(cat $S/qa_8011.pid 2>/dev/null)"
for u in / /health /kg/suggest /cache/stats /audit /audit/api/reports /gen /doc/info; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:8011$u")
  printf '  %-22s -> %s\n' "$u" "$code"
done
echo "  /health 内容：$(curl -s --max-time 5 http://127.0.0.1:8011/health | head -c 90)"

echo
echo "=== 4. 报告目录没被测试污染 ==="
echo "  文件数：$(ls /data/eia_reports | wc -l) （基线 8）"
echo "  .part 残留：$(ls /data/eia_reports/*.part 2>/dev/null | wc -l) （应为 0）"
echo "  uploadtest 残留：$(ls /data/eia_reports/ | grep -c uploadtest || true) （应为 0）"

echo
echo "=== 5. 备份目录（回滚用）==="
D=/home/test/_重构归档_20260918/两项改造_前
echo "  文件数：$(ls $D 2>/dev/null | wc -l) （应为 11）"
ls "$D" 2>/dev/null | head -12

echo
echo "=== 6. 临时目录已清 ==="
for d in /home/test/_上传暂存 /home/test/_语法检查_tmp; do
  if [ -e "$d" ]; then echo "  ★ 还在：$d"; else echo "  已清：$d"; fi
done
