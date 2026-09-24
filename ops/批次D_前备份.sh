#!/bin/bash
# 批次 D（第 7 项）上传前备份：知识图谱中文化 / 匹配列表 / 详情栏 / 正文实体跳转
# 本批**含后端改动**（kg.py 新增 find_entities、routes.py 新增 POST /kg/entities）
set -e
D=/home/test/xishu_qingyu_serve
DST=/home/test/_重构归档_20260918/批次D_前
mkdir -p "$DST/frontend/js" "$DST/xishu_pipeline"
echo "=========== 批次 D：上传前备份 ==========="
for f in index.html app.css; do
  cp -p "$D/frontend/$f" "$DST/frontend/$f"
  printf '  %-26s %7d B  md5 %s\n' "frontend/$f" "$(stat -c%s "$D/frontend/$f")" "$(md5sum "$D/frontend/$f" | cut -d' ' -f1)"
done
for f in kg.js message.js main.js; do
  cp -p "$D/frontend/js/$f" "$DST/frontend/js/$f"
  printf '  %-26s %7d B  md5 %s\n' "frontend/js/$f" "$(stat -c%s "$D/frontend/js/$f")" "$(md5sum "$D/frontend/js/$f" | cut -d' ' -f1)"
done
for f in kg.py routes.py; do
  cp -p "$D/xishu_pipeline/$f" "$DST/xishu_pipeline/$f"
  printf '  %-26s %7d B  md5 %s\n' "xishu_pipeline/$f" "$(stat -c%s "$D/xishu_pipeline/$f")" "$(md5sum "$D/xishu_pipeline/$f" | cut -d' ' -f1)"
done
echo "  备份目录：$DST"
