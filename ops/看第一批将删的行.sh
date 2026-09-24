#!/usr/bin/env bash
# 只读：把"切换后将删掉的行"逐文件打出来（人工确认没有误伤）。
set -u
S=/home/test/_staging_20260922_第一批

show() {
  local L="$1" R="$2"
  echo "===== $L"
  if [ ! -f "$R" ]; then echo "   (暂存缺失)"; return; fi
  local d
  d=$(diff -u "$L" "$R" | grep '^-[^-]' || true)
  if [ -z "$d" ]; then echo "   (无删除行)"; else echo "$d"; fi
}

show /data/eia_audit/audit/criteria.py                          "$S/audit/criteria.py"
show /data/eia_report_gen/gen/intake.py                         "$S/gen/intake.py"
show /home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js    "$S/xishu_pipeline/static/gen_ui.js"
show /home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.js  "$S/xishu_pipeline/static/audit_ui.js"
show /home/test/xishu_qingyu_serve/xishu_pipeline/static/audit_ui.css "$S/xishu_pipeline/static/audit_ui.css"
show /home/test/xishu_qingyu_serve/xishu_pipeline/audit_docx.py       "$S/xishu_pipeline/audit_docx.py"
show /home/test/xishu_qingyu_serve/frontend/js/main.js                "$S/frontend/js/main.js"
