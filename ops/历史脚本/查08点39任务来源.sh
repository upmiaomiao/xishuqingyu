#!/bin/bash
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
echo "=== 1. job 0f0c0e615af9（08:39:26 那份未命名草稿）在日志中的位置 ==="
grep -n '0f0c0e615af9' $LOG | head -3

N=$(grep -n '0f0c0e615af9' $LOG | head -1 | cut -d: -f1)
if [ -n "$N" ]; then
  echo
  echo "=== 2. 首次出现（第 $N 行）之前 10 行 —— 看是哪个端点创建的 ==="
  sed -n "$((N-10)),$((N+1))p" $LOG
fi

echo
echo "=== 3. 日志总行数 vs 最后一次 /gen/api/* 请求位置 ==="
wc -l < $LOG
echo "最后一次 /gen/api/run      : $(grep -n '/gen/api/run' $LOG | tail -1 | cut -d: -f1)"
echo "最后一次 /gen/api/chat/generate : $(grep -n '/gen/api/chat/generate' $LOG | tail -1 | cut -d: -f1)"

echo
echo "=== 4. 日志里最后 12 行 ==="
tail -12 $LOG
