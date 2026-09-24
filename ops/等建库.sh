#!/bin/bash
# 等建索引v3 收尾并打印日志（最多等 14 分钟）
for i in $(seq 1 84); do
  pgrep -f '建索引v3.py' >/dev/null || break
  sleep 10
done
if pgrep -f '建索引v3.py' >/dev/null; then
  echo "【仍在跑】"
else
  echo "【已结束】"
fi
echo "=== 建库日志 ==="
tail -32 /home/test/建索引v3.log
echo
echo "=== 产物 ==="
ls -l /data/fagui_rag/index_v3/
