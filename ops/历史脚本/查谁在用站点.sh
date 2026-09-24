#!/bin/bash
echo "=== 1. 站点日志里 08:35-08:45 的请求 ==="
grep -E '08:3[5-9]|08:4[0-5]' /home/test/xishu_qingyu_serve/qa_8011.log 2>/dev/null | tail -30

echo
echo "=== 2. 当前在跑的生成任务 ==="
curl -s -m 20 http://127.0.0.1:8011/gen/api/jobs | head -c 800
echo
echo
echo "=== 3. 站点进程的活跃连接（看是否有别的客户端）==="
ss -tnp 2>/dev/null | grep ':8011' | head -15

echo
echo "=== 4. 站点日志里出现的客户端 IP 统计 ==="
grep -oE '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' /home/test/xishu_qingyu_serve/qa_8011.log 2>/dev/null | sort | uniq -c | sort -rn | head -10

echo
echo "=== 5. 日志格式抽样（确认能否看出客户端）==="
tail -5 /home/test/xishu_qingyu_serve/qa_8011.log
