#!/bin/bash
# 决定性测试：静默观察 60 秒，看站点日志是否自己增长。
# 若增长 → 有别的客户端在用；若不变 → 只有我在测。
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
BEFORE=$(wc -l < $LOG)
echo "观察开始：日志 $BEFORE 行，本机当前时间 $(date -u +%H:%M:%S) UTC"
echo "（这 60 秒内我不发任何 HTTP 请求，只走 SSH 观察）"
sleep 60
AFTER=$(wc -l < $LOG)
echo "观察结束：日志 $AFTER 行，$(date -u +%H:%M:%S) UTC"
echo "新增 $((AFTER-BEFORE)) 行"
echo
if [ "$AFTER" -gt "$BEFORE" ]; then
  echo "=== 新增的请求（说明有别的客户端在用）==="
  tail -n +$((BEFORE+1)) $LOG
else
  echo "=== 没有任何新请求（说明当前没有别的客户端在用）==="
fi
