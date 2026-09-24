#!/bin/bash
# 阶段 3 上传前备份。必须在**上传之前**独立执行。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
DST="$ARC/阶段3前"
mkdir -p "$DST"

echo "=========== 阶段 3 备份（上传前，此刻线上状态）==========="
for f in xishu_pipeline/static/gen_ui.js xishu_pipeline/static/audit_ui.js \
         frontend/gen.html frontend/audit.html frontend/js/views.js \
         xishu_pipeline/audit_routes.py; do
  src="$D/$f"
  if [ -f "$src" ]; then
    out="$DST/$(echo "$f" | tr '/' '_')"
    cp -p "$src" "$out"
    printf '  %-40s %8d 字节  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  else
    printf '  %-40s 不存在\n' "$f"
  fi
done

echo
echo "  即将新增（线上应尚不存在）："
for f in xishu_pipeline/static/audit_page.css xishu_pipeline/static/audit_page.js; do
  if [ -f "$D/$f" ]; then echo "    $f 已存在（会被覆盖）"; else echo "    $f 尚不存在 —— 本次新建"; fi
done

echo
echo "  备份目录："
ls -l "$DST" | tail -n +2 | awk '{printf "    %8s  %s\n",$5,$9}'
