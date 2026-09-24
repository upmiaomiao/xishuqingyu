#!/bin/bash
# 阶段 0：卫生 —— 快照 + 把备份/测试文件移出生产目录
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918
TS=$(date -u +%Y%m%d-%H%M%S)

echo "=========== 0.1 完整快照 ==========="
mkdir -p "$ARC"
tar czf "$ARC/重构前快照_$TS.tar.gz" \
    --exclude='__pycache__' --exclude='*.pyc' \
    -C "$D" frontend xishu_pipeline
echo "  快照：$ARC/重构前快照_$TS.tar.gz"
ls -lh "$ARC/重构前快照_$TS.tar.gz" | awk '{print "  大小："$5}'
echo "  内含文件数：$(tar tzf "$ARC/重构前快照_$TS.tar.gz" | grep -c '\.')"
echo "  记录基线 md5："
( cd "$D" && find frontend xishu_pipeline -type f \( -name '*.py' -o -name '*.js' -o -name '*.css' -o -name '*.html' \) \
    ! -name '*.bak*' ! -path '*__pycache__*' -exec md5sum {} \; | sort -k2 ) > "$ARC/基线md5_$TS.txt"
echo "    写入 $ARC/基线md5_$TS.txt（$(wc -l < "$ARC/基线md5_$TS.txt") 个文件）"

echo
echo "=========== 0.2 备份文件移出生产目录 ==========="
mkdir -p "$ARC/旧备份文件"
moved=0
for f in "$D"/frontend/*.bak* "$D"/xishu_pipeline/static/*.bak* "$D"/xishu_pipeline/*.bak*; do
  [ -f "$f" ] || continue
  echo "  移走 $(basename "$f")"
  mv "$f" "$ARC/旧备份文件/"
  moved=$((moved+1))
done
echo "  共移走 $moved 个"

echo
echo "=========== 0.3 孤儿测试文件移出 static/ ==========="
mkdir -p "$D/tests"
if [ -f "$D/xishu_pipeline/static/查模块挂载.js" ]; then
  mv "$D/xishu_pipeline/static/查模块挂载.js" "$D/tests/查模块挂载.js"
  echo "  已移到 $D/tests/查模块挂载.js"
else
  echo "  （不在 static/ 里，跳过）"
fi

echo
echo "=========== 0.4 生产目录现状 ==========="
echo "  frontend/："
ls -1 "$D/frontend"
echo "  xishu_pipeline/static/："
ls -1 "$D/xishu_pipeline/static"

echo
echo "=========== 0.5 站点仍然健康 ==========="
bash "$D/launch_xishu_qingyu_qa_8011.sh" status 2>&1 | head -4
echo "  /health        $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health)"
echo "  /              $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/)"
echo "  /gen           $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/gen)"
echo "  /audit         $(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/audit)"
