#!/bin/bash
# 报告编制长耗时反馈改动：上传前备份（必须在**上传之前**独立执行）。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
DST="$ARC/编制反馈前"
mkdir -p "$DST"

echo "=========== 报告编制反馈改动：上传前备份 ==========="
for f in xishu_pipeline/gen_routes.py xishu_pipeline/static/gen_ui.js xishu_pipeline/static/gen_ui.css; do
  src="$D/$f"
  if [ -f "$src" ]; then
    out="$DST/$(echo "$f" | tr '/' '_')"
    cp -p "$src" "$out"
    printf '  %-38s %8d 字节  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  else
    printf '  %-38s 不存在\n' "$f"
  fi
done

echo
echo "  备份目录：$DST"
ls -1 "$DST" | sed 's/^/    /'
