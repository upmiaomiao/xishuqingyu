#!/bin/bash
# 部署「已废止降权」到线上检索层（含备份、编译检查、重启、健康检查）
set -e
TS=$(date +%Y%m%d_%H%M%S)
NEW=/home/test/retriever.py.已废止降权
LIVE=/data/fagui_rag/retriever.py
BAK=/home/test/_重构归档_20260921/已废止降权_前
PY=/home/test/fagui_serve/.venv/bin/python

echo "===== 1) 备份线上原件 ====="
mkdir -p "$BAK"
cp -p "$LIVE" "$BAK/retriever.py.$TS"
md5sum "$LIVE" "$BAK/retriever.py.$TS"

echo
echo "===== 2) 编译检查新文件 ====="
"$PY" -m py_compile "$NEW" && echo "  语法 OK"
echo "  新文件行数：$(wc -l < "$NEW")；新文件 md5：$(md5sum "$NEW" | cut -d' ' -f1)"

echo
echo "===== 3) 就地替换 ====="
cp -p "$NEW" "$LIVE"
md5sum "$LIVE"
grep -n "ABOLISHED_PENALTY\|def is_abolished\|def eff" "$LIVE" | head

echo
echo "===== 4) 重启站点 ====="
bash /home/test/安全重启8011.sh 2>&1 | tail -6

echo
echo "===== 5) 健康检查 ====="
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8011/health || true)
  echo "  第 $i 次 /health = $code"
  [ "$code" = "200" ] && break
  sleep 3
done
curl -s --max-time 10 http://127.0.0.1:8011/health
echo
echo "站点进程：$(pgrep -f 'xishu_qingyu' | tr '\n' ' ')"
echo "备份目录：$BAK"
ls -l "$BAK"
