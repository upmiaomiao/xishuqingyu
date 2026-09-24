#!/bin/bash
# 量服务进程的内存占用与运行时长（内存里 _JOBS/_SESS 从不清理，要看到底涨到多少）
PID=$(pgrep -f 'uvicorn.*8011' | head -1)
if [ -z "$PID" ]; then
  PID=$(ss -lptn 'sport = :8011' 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1)
fi
echo "pid=$PID"
if [ -n "$PID" ]; then
  grep -E 'VmRSS|VmSize' /proc/$PID/status
  echo "--- 已运行 ---"
  ps -o etime=,rss=,vsz= -p "$PID"
fi
echo
echo "--- 生成结果目录 ---"
ls -1 /data/eia_report_gen/_生成结果/*.docx 2>/dev/null | wc -l
echo
echo "--- 审核报告目录 ---"
ls -1 /data/eia_report_gen/审核 2>/dev/null | head -5
echo
echo "--- 服务日志里的错误行（最近 40 条）---"
LOG=$(ls -t /home/test/*.log 2>/dev/null | head -1)
echo "日志：$LOG"
grep -nE 'Traceback|Error|ERROR|Exception' "$LOG" 2>/dev/null | tail -40
