#!/bin/bash
# 两项改造（审核上传 + 图谱推荐词）—— 改动前备份。
#
# 约定：备份是**独立的一步**，先跑它、确认成功，再跑部署。
# 两者分开，是为了"备份没成功"这件事有机会被发现 ——
# 混在一个脚本里，备份失败会静默地继续往下改。
set -u
S=/home/test/xishu_qingyu_serve
STAMP=$(date +%Y%m%d_%H%M%S)
DEST=/home/test/_重构归档_20260918/两项改造_前
mkdir -p "$DEST"

echo "=== 本次要改的文件（备份中）==="
FILES="
xishu_pipeline/kg.py
xishu_pipeline/routes.py
xishu_pipeline/errors.py
xishu_pipeline/audit_routes.py
xishu_pipeline/resilience.py
xishu_pipeline/static/audit_ui.js
frontend/index.html
frontend/app.css
frontend/js/kg.js
frontend/js/views.js
frontend/js/main.js
"
n=0
miss=0
for f in $FILES; do
  src="$S/$f"
  if [ ! -f "$src" ]; then
    echo "  ★ 源文件不存在：$src"
    miss=$((miss+1))
    continue
  fi
  # 用下划线替掉斜杠，压成一个平面文件名，便于一眼看全
  safe=$(echo "$f" | tr '/' '_')
  out="$DEST/$safe.$STAMP"
  cp -p "$src" "$out"
  printf '  %-42s %8d B  %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -c1-12)"
  n=$((n+1))
done

echo
echo "  备好 $n 个文件，缺失 $miss 个"
echo "  备份目录：$DEST"
echo "$STAMP" > /home/test/_重构归档_20260918/.last_stamp_两项
echo "  时间戳：$STAMP （已记入 .last_stamp_两项）"

if [ "$miss" -gt 0 ]; then
  echo
  echo "★ 有源文件缺失，部署脚本应当中止。"
  exit 1
fi
echo
echo "备份完成。"
