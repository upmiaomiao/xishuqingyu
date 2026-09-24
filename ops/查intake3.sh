#!/bin/bash
D=/data/eia_report_gen/gen/intake.py
echo "=== $D  ($(stat -c%s "$D") 字节, md5 $(md5sum "$D" | cut -d' ' -f1)) ==="
echo
echo "=== 所有 def ==="
grep -n '^\s*def ' "$D"
echo
echo "=== parse_description 全文 ==="
awk '/def parse_description/,/^def [a-z_]+\(/' "$D" | head -70
echo
echo "=== 这个包里的模型调用点 ==="
grep -rn 'def _llm\|def llm\|def call_model\|stream_model\|chat/completions' /data/eia_report_gen/gen/*.py | head -20
