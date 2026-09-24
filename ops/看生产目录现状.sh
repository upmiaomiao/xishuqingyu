#!/bin/bash
OUT=/data/eia_report_gen/_生成结果
echo "=== 最新 20 份（按时间倒序）==="
ls -lt --time-style=+%m-%d\ %H:%M "$OUT"/*.docx | head -20 | sed 's#/data/eia_report_gen/_生成结果/##'
echo
echo "=== 顶层总数：$(ls "$OUT"/*.docx 2>/dev/null | wc -l) ==="
echo
echo "=== 各归档子目录 ==="
for d in "$OUT"/_*; do
  [ -d "$d" ] && echo "  $(basename "$d")：$(ls "$d" | wc -l) 个"
done
echo
echo "=== 今天(09-18)产生的份数 ==="
ls -l --time-style=+%m-%d "$OUT"/*.docx | grep -c '09-18'
