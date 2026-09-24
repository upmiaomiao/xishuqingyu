#!/bin/bash
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
echo "=== 1. 日志里所有客户端 IP 及请求数 ==="
grep -oE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}:[0-9]+' $LOG \
  | sed 's/:[0-9]*$//' | sort | uniq -c | sort -rn

echo
echo "=== 2. 所有 /gen/api/run（会生成 docx 的那个端点）及其客户端 ==="
grep '/gen/api/run' $LOG | sed 's/HTTP\/1.1.*//' | tail -20

echo
echo "=== 3. /gen/api/run 的客户端 IP 分布 ==="
grep '/gen/api/run' $LOG | grep -oE '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}' | sort | uniq -c

echo
echo "=== 4. 最近 25 条请求（看调用序列）==="
tail -25 $LOG

echo
echo "=== 5. 本机自己的 IP ==="
hostname -I

echo
echo "=== 6. 那个 08:39 任务之后是否还有别的客户端请求 ==="
echo "（日志无时间戳，用行号定位 /gen/api/run 出现的位置）"
grep -n '/gen/api/run' $LOG | tail -5
echo "日志总行数：$(wc -l < $LOG)"
