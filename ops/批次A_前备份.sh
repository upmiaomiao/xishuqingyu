#!/bin/bash
# 批次 A（第 1/2/3 项）上传前备份：消息去重、检索进度折叠文案、侧栏收起
set -e
D=/home/test/xishu_qingyu_serve
DST=/home/test/_重构归档_20260918/批次A_前
mkdir -p "$DST/js"
echo "=========== 批次 A：上传前备份 ==========="
for f in index.html app.css; do
  cp -p "$D/frontend/$f" "$DST/$f"
  printf '  %-18s %7d B  md5 %s\n' "$f" "$(stat -c%s "$D/frontend/$f")" "$(md5sum "$D/frontend/$f" | cut -d' ' -f1)"
done
for f in message.js main.js; do
  cp -p "$D/frontend/js/$f" "$DST/js/$f"
  printf '  %-18s %7d B  md5 %s\n' "js/$f" "$(stat -c%s "$D/frontend/js/$f")" "$(md5sum "$D/frontend/js/$f" | cut -d' ' -f1)"
done
echo "  备份目录：$DST"
