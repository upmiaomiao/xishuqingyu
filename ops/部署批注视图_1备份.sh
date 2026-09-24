#!/bin/bash
# 部署「原文批注视图」第 1 步：备份现有文件（上传之前跑）。
# 约定：归档不删除；启动脚本 md5 冻结，只用 安全重启8011.sh。
set -u
S=/home/test/xishu_qingyu_serve
TS=$(date +%Y%m%d_%H%M%S)
BAK=/home/test/_重构归档_20260922/原文批注视图_前

echo "=== 备份现有文件 → $BAK ==="
mkdir -p "$BAK/xishu_pipeline/static" "$BAK/frontend"
for f in xishu_pipeline/audit_routes.py xishu_pipeline/static/audit_ui.js \
         xishu_pipeline/static/audit_ui.css frontend/audit.html; do
  cp -p "$S/$f" "$BAK/$f.$TS" && echo "  备份 $f"
done
echo "$TS" > "$BAK/.timestamp"
echo "时间戳：$TS"
echo
echo "=== 当前线上 md5（改动前基线）==="
md5sum "$S/xishu_pipeline/audit_routes.py" "$S/xishu_pipeline/static/audit_ui.js" \
       "$S/xishu_pipeline/static/audit_ui.css"
