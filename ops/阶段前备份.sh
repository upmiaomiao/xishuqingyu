#!/bin/bash
# 通用「阶段前备份」：在**上传之前**跑，把当前线上源码存进归档目录。
# 用法：bash 阶段前备份.sh <阶段名>
# 教训：2026-09-18 我两次「先上传后备份」，备份的是已覆盖的新文件，等于没备份。
#       所以备份必须是一个**独立的、先执行的**步骤。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
STAGE=${1:?用法: bash 阶段前备份.sh <阶段名>}
DST="$ARC/${STAGE}前"
mkdir -p "$DST"

echo "=========== 阶段「$STAGE」备份（上传前）==========="
for f in frontend/index.html frontend/gen.html frontend/audit.html \
         xishu_pipeline/static/gen_ui.js xishu_pipeline/static/gen_ui.css \
         xishu_pipeline/static/audit_ui.js xishu_pipeline/static/audit_ui.css \
         xishu_pipeline/routes.py xishu_pipeline/gen_routes.py xishu_pipeline/audit_routes.py; do
  src="$D/$f"
  if [ -f "$src" ]; then
    out="$DST/$(basename "$f")"
    cp -p "$src" "$out"
    printf '  %-42s %8d 字节  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  fi
done
echo
echo "  备份目录：$DST"
echo "  与阶段 0 基线核对："
BASE=$(ls -t $ARC/基线md5_*.txt | head -1)
for f in frontend/index.html frontend/gen.html frontend/audit.html \
         xishu_pipeline/static/gen_ui.js xishu_pipeline/static/gen_ui.css \
         xishu_pipeline/static/audit_ui.js xishu_pipeline/static/audit_ui.css \
         xishu_pipeline/routes.py; do
  now=$(md5sum "$D/$f" 2>/dev/null | cut -d' ' -f1)
  was=$(grep " $f\$" "$BASE" | cut -d' ' -f1)
  if [ "$now" = "$was" ]; then st="未改动"; else st="已改动（本会话内）"; fi
  printf '    %-42s %s\n' "$f" "$st"
done
