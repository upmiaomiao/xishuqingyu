#!/bin/bash
L=/home/test/xishu_qingyu_serve/qa_8011.log
echo "日志：$L"
echo "行数：$(wc -l < "$L")"
echo "================= 最后 50 行 ================="
tail -50 "$L"
echo
echo "================= Traceback 位置 ================="
grep -n 'Traceback' "$L" | tail -5
echo
echo "================= 最后一个 Traceback 全文 ================="
LAST=$(grep -n 'Traceback' "$L" | tail -1 | cut -d: -f1)
if [ -n "$LAST" ]; then
  sed -n "${LAST},\$p" "$L" | head -50
else
  echo "（没有 Traceback）"
fi
