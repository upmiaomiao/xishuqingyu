#!/usr/bin/env bash
# 只读：核对"第一批"部署到哪一步了 —— 备份是否齐全、每个文件是旧的还是新的。
set -u
S=/home/test/_staging_20260922_第一批
BAK=/home/test/_重构归档_20260922/第一批_前

echo "===== A) 备份目录 ====="
ls -la "$BAK" 2>&1 | head -20

pair() {
  local live="$1" stage="$2" name="$3"
  local a b
  a=$(md5sum "$live"  2>/dev/null | cut -c1-10)
  b=$(md5sum "$stage" 2>/dev/null | cut -c1-10)
  if [ "$a" = "$b" ]; then echo "  [已切换] $name"; else echo "  [仍旧版] $name   线上=$a 暂存=$b"; fi
}

echo
echo "===== B) 每个文件的状态 ====="
pair /data/eia_audit/audit/criteria.py "$S/audit/criteria.py" criteria.py
pair /data/eia_report_gen/gen/intake.py "$S/gen/intake.py" intake.py
pair /home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js "$S/xishu_pipeline/static/gen_ui.js" gen_ui.js
pair /home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js "$S/xishu_pipeline/static/audit_ui.js" audit_ui.js
pair /home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.css "$S/xishu_pipeline/static/audit_ui.css" audit_ui.css
pair /home/test/xishu_qingyu_serve/xishu_pipeline/audit_docx.py "$S/xishu_pipeline/audit_docx.py" audit_docx.py
pair /home/test/xishu_qingyu_serve/frontend/js/main.js "$S/frontend/js/main.js" main.js
