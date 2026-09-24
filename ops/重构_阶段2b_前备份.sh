#!/bin/bash
# 阶段 2b 上传前备份。必须在**上传之前**独立执行。
# 教训：2026-09-18 有两次「先上传后备份」，备份的是已被覆盖的新文件，等于没备份。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
DST="$ARC/阶段2b前"
mkdir -p "$DST"

echo "=========== 阶段 2b 备份（上传前，此刻线上状态）==========="
for f in frontend/index.html xishu_pipeline/routes.py; do
  src="$D/$f"
  if [ -f "$src" ]; then
    out="$DST/$(basename "$f")"
    cp -p "$src" "$out"
    printf '  %-34s %8d 字节  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  else
    printf '  %-34s 不存在\n' "$f"
  fi
done

echo
echo "  frontend/js/（阶段 2b 新增目录）："
if [ -d "$D/frontend/js" ]; then
  ls -l "$D/frontend/js" | tail -n +2 | awk '{printf "    %s %s\n",$5,$9}'
else
  echo "    尚不存在 —— 本次是首次创建，无旧内容可备份"
fi

echo
echo "  线上 frontend/ 目录全貌："
ls -l "$D/frontend/" | tail -n +2 | awk '{printf "    %8s  %s\n",$5,$9}'

echo
echo "  备份目录内容："
ls -l "$DST" | tail -n +2 | awk '{printf "    %8s  %s\n",$5,$9}'
