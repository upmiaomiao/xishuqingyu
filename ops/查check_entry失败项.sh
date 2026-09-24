#!/usr/bin/env bash
# 只看 check_entry 的失败项（上一次跑出 24/3）
V=/home/test/fagui_serve/.venv/bin/python
cd /data/eia_audit || exit 1
"$V" check_entry.py 2>&1 | grep -nE "×|✗|失败|FAIL|ERROR|Traceback" | head -30
echo "----- 全文尾部 40 行 -----"
"$V" check_entry.py 2>&1 | tail -40
