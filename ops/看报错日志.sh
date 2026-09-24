#!/bin/bash
LOG=$(ls -t /home/test/*.log 2>/dev/null | head -1)
echo "最新日志：$LOG"
echo "================= 最后 60 行 ================="
tail -60 "$LOG" 2>/dev/null
echo
echo "================= 所有 Traceback 的行号 ================="
grep -n 'Traceback' "$LOG" 2>/dev/null | tail -10
echo
echo "================= 最后一个 Traceback 的全文 ================="
LAST=$(grep -n 'Traceback' "$LOG" 2>/dev/null | tail -1 | cut -d: -f1)
if [ -n "$LAST" ]; then
  sed -n "${LAST},\$p" "$LOG" | head -60
else
  echo "（日志里没有 Traceback）"
fi
