#!/usr/bin/env bash
# 服务器侧契约检查（必须在这里跑：它们读的是**线上实际返回**的代码）。
set -u
PY=/home/test/fagui_serve/.venv/bin/python
cd /home/test

echo "===== 1) 生成页嵌入契约（含新增：新建报告必须复位 4 处可变状态）====="
cp /home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js /tmp/ 2>/dev/null || true
"$PY" /home/test/查嵌入契约.py 2>&1 | tail -18

echo
echo "===== 2) 审核界面契约 ====="
"$PY" /home/test/查界面契约.py 2>&1 | tail -12

echo
echo "===== 3) 入口检查（审核引擎自检）====="
"$PY" /data/eia_audit/check_entry.py 2>&1 | tail -12
