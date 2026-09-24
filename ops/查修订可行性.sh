#!/bin/bash
# 查"修订式交付"的底子（只读）
set -u
echo "=== 哪个解释器有 pymupdf ==="
for P in /home/test/fagui_serve/.venv/bin/python /home/test/xishu_qingyu_serve/.venv/bin/python /usr/bin/python3; do
  echo "--- $P"
  $P -c 'import sys; print(sys.executable); import fitz; print("pymupdf ok")' 2>&1 | head -3
done
echo
echo "=== 站点进程用的是哪个 python ==="
tr '\0' ' ' < /proc/$(cat /home/test/xishu_qingyu_serve/qa_8011.pid)/cmdline 2>/dev/null | head -c 300
echo
echo
echo "=== 可行性统计 ==="
/home/test/fagui_serve/.venv/bin/python /home/test/查修订可行性.py 2>&1 | tail -70
