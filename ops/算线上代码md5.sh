#!/bin/bash
# 按导出清单逐文件算 md5，供本地与 git 仓库逐条比对。
set -u
LIST=/home/test/_导出代码/文件清单.txt
OUT=/home/test/_导出代码/线上md5.txt
if [ ! -f "$LIST" ]; then echo "缺少清单 $LIST"; exit 1; fi
: > "$OUT"
n=0
while IFS= read -r rel; do
  [ -z "$rel" ] && continue
  if [ -f "/$rel" ]; then
    printf '%s  %s\n' "$(md5sum "/$rel" | cut -d' ' -f1)" "$rel" >> "$OUT"
    n=$((n+1))
  fi
done < "$LIST"
echo "已算 $n 个文件的 md5 → $OUT（清单 $(wc -l < "$LIST") 条）"
