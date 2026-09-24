#!/bin/bash
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
BEFORE=$(wc -l < $LOG)
echo "请求前日志行数：$BEFORE"
echo "（现在从本机 Windows 发一个带唯一标记的请求…）"
sleep 6
AFTER=$(wc -l < $LOG)
echo "请求后日志行数：$AFTER"
echo
echo "=== 新增的日志行 ==="
tail -n +$((BEFORE+1)) $LOG
