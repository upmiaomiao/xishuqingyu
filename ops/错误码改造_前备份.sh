#!/bin/bash
# 错误码改造：上传前备份（必须在**上传之前**独立执行）。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
DST="$ARC/错误码改造前"
mkdir -p "$DST/xishu_pipeline" "$DST/frontend_js" "$DST/static"

echo "=========== 错误码改造：上传前备份 ==========="
echo
echo "--- 服务端包 ---"
for f in errors.py routes.py gen_routes.py audit_routes.py normalize.py llm.py pipeline.py; do
  src="$D/xishu_pipeline/$f"
  if [ -f "$src" ]; then
    cp -p "$src" "$DST/xishu_pipeline/$f"
    printf '  %-18s %7d B  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  else
    printf '  %-18s （线上还没有这个文件，属于新增）\n' "$f"
  fi
done

echo
echo "--- 前端模块 ---"
for f in util.js views.js message.js ask.js kg.js; do
  src="$D/frontend/js/$f"
  if [ -f "$src" ]; then
    cp -p "$src" "$DST/frontend_js/$f"
    printf '  %-18s %7d B  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  fi
done

echo
echo "--- 静态界面 ---"
for f in gen_ui.js audit_ui.js; do
  src="$D/xishu_pipeline/static/$f"
  if [ -f "$src" ]; then
    cp -p "$src" "$DST/static/$f"
    printf '  %-18s %7d B  md5 %s\n' "$f" "$(stat -c%s "$src")" "$(md5sum "$src" | cut -d' ' -f1)"
  fi
done

echo
echo "  备份目录：$DST"
find "$DST" -type f | sed 's|^|    |'
