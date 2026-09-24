#!/bin/bash
# 读服务进程的 RSS / VmSize / 运行时长。单独成文件，因为它含 $( )，
# 在 PowerShell 里内联会被本地解析掉（这个坑本会话已经踩过多次）。
PID=$(pgrep -f 'uvicorn.*8011' | head -1)
if [ -z "$PID" ]; then
  PID=$(ss -lptn 2>/dev/null | grep ':8011' | grep -oP 'pid=\K[0-9]+' | head -1)
fi
if [ -z "$PID" ]; then
  echo "找不到 8011 的服务进程"
  exit 1
fi
echo "pid   = $PID"
grep -E 'VmRSS|VmSize' /proc/"$PID"/status | sed 's/^/  /'
echo "  etime = $(ps -o etime= -p "$PID" | tr -d ' ')"
echo "  UTC   = $(date -u +%H:%M:%S)"
