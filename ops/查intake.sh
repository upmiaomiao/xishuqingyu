#!/bin/bash
echo "=== 找 gen 包 ==="
find /home/test/xishu_qingyu_serve -maxdepth 3 -name 'intake.py' -not -path '*/__pycache__/*' 2>/dev/null
echo
D=$(find /home/test/xishu_qingyu_serve -maxdepth 3 -name 'intake.py' -not -path '*/__pycache__/*' 2>/dev/null | head -1)
echo "文件：$D"
echo
echo "=== parse_description 及其调用的模型次数 ==="
grep -n 'def parse_description' -A 60 "$D" | head -70
echo
echo "=== 这个文件里所有 def ==="
grep -n '^\s*def ' "$D"
echo
echo "=== 所有模型调用点 ==="
grep -n 'llm\|chat_completion\|stream_model\|post_json\|requests.post\|urllib' "$D" | head -30
