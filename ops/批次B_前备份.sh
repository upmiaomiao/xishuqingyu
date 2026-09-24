#!/bin/bash
# 批次 B（第 4/5 项）上传前备份：历史记录置顶 / 项目分组 / 重命名 / 分享
set -e
D=/home/test/xishu_qingyu_serve
DST=/home/test/_重构归档_20260918/批次B_前
mkdir -p "$DST/js"
echo "=========== 批次 B：上传前备份 ==========="
cp -p "$D/frontend/app.css" "$DST/app.css"
printf '  %-18s %7d B  md5 %s\n' "app.css" "$(stat -c%s "$D/frontend/app.css")" "$(md5sum "$D/frontend/app.css" | cut -d' ' -f1)"
for f in store.js main.js; do
  cp -p "$D/frontend/js/$f" "$DST/js/$f"
  printf '  %-18s %7d B  md5 %s\n' "js/$f" "$(stat -c%s "$D/frontend/js/$f")" "$(md5sum "$D/frontend/js/$f" | cut -d' ' -f1)"
done
echo "  备份目录：$DST"
