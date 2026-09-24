#!/usr/bin/env bash
# 服务器侧检查一把跑（审核引擎自检 + 规范合规体检）
V=/home/test/fagui_serve/.venv/bin/python
cd /data/eia_audit || exit 1

echo "===== ① check_entry（入口/静态/安全）====="
if [ -f check_entry.py ]; then "$V" check_entry.py 2>&1 | tail -8; else echo "（无 check_entry.py）"; fi

echo
echo "===== ② check_ui_contract（前后端字段）====="
if [ -f check_ui_contract.py ]; then "$V" check_ui_contract.py 2>&1 | tail -8; else echo "（无 check_ui_contract.py）"; fi

echo
echo "===== ③ selfcheck api（审核接口）====="
if [ -f selfcheck.py ]; then "$V" selfcheck.py api 2>&1 | tail -10; else echo "（无 selfcheck.py）"; fi

echo
echo "===== ④ 规范合规体检 ====="
if [ -f /home/test/规范合规体检.py ]; then
  "$V" /home/test/规范合规体检.py 2>&1 | tail -12
else
  echo "（/home/test/规范合规体检.py 不在，跳过）"
fi

echo
echo "===== ⑤ 端到端真跑一份审核（走线上接口）====="
curl -s -m 120 -X POST http://127.0.0.1:8011/audit/api/run \
  -H 'Content-Type: application/json' -d '{}' | head -c 300
echo
