#!/bin/bash
# 部署「四项改造」第 0 步：把当前线上文件备份走。
#
# ⚠ 必须在**上传新文件之前**跑。备份和上传分两步是刻意的 ——
#   之前把备份和上传写在一个脚本里，一旦上传失败，备份也没了。
#
# 备份到 /home/test/_重构归档_20260918/四项改造_前/（带时间戳）。
set -e

SITE=/home/test/xishu_qingyu_serve
STAMP=$(date +%Y%m%d_%H%M%S)
DEST=/home/test/_重构归档_20260918/四项改造_前
mkdir -p "$DEST"

echo "=== 备份到 $DEST ==="

for f in \
  xishu_pipeline/config.py \
  xishu_pipeline/routes.py \
  xishu_pipeline/pipeline.py \
  frontend/index.html \
  frontend/app.css \
  frontend/js/ask.js \
  frontend/js/message.js \
  ; do
  src="$SITE/$f"
  if [ -f "$src" ]; then
    # 路径里的 / 换成 __，平铺存放，便于一眼看全
    flat=$(echo "$f" | tr '/' '_')
    cp -p "$src" "$DEST/${flat}.${STAMP}"
    printf '  √ %-34s -> %s.%s\n' "$f" "$flat" "$STAMP"
  else
    printf '  × 不存在，跳过：%s\n' "$f"
  fi
done

echo
echo "=== 顺带记录改动前的文件指纹（便于回滚后核对）==="
md5sum "$SITE/xishu_pipeline/config.py" \
       "$SITE/xishu_pipeline/routes.py" \
       "$SITE/xishu_pipeline/pipeline.py" \
       "$SITE/frontend/index.html" \
       "$SITE/frontend/app.css" \
       "$SITE/frontend/js/ask.js" \
       "$SITE/frontend/js/message.js" 2>/dev/null | sed 's|/home/test/xishu_qingyu_serve/||'

echo
echo "=== 备份目录内容 ==="
ls -la "$DEST" | tail -12

echo
echo "备份完成。下一步才上传新文件。"
