#!/bin/bash
# 步骤时间线改动：上传前备份（必须在**上传之前**独立执行）。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
DST="$ARC/步骤时间线前"
mkdir -p "$DST"

echo "=========== 步骤时间线改动：上传前备份 ==========="
for f in xishu_pipeline/pipeline.py frontend/js/ask.js frontend/js/message.js frontend/app.css; do
  src="$D/$f"
  if [ -f "$src" ]; then
    out="$DST/$(echo "$f" | tr '/' '_')"
    cp -p "$src" "$out"
    printf '  %-32s %8d 字节  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  else
    printf '  %-32s 不存在\n' "$f"
  fi
done

echo
echo "  备份目录：$DST"
ls -1 "$DST" | sed 's/^/    /'
