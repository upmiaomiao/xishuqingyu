#!/bin/bash
# 线上跑**全部**单测（A 档四件上线后的最终回归）。只读，不改数据。
export EIA_CRITERIA_DIR=/data/fagui_rag/criteria
export EIA_ENGINE_DIR=/data/eia_audit
export PYTHONPATH=/data/eia_audit:/data/eia_report_gen
export AUDIT_HOME=/data/eia_audit
cd /home/test/A档单测 || exit 1
total=0
for f in $(ls 单测_*.py | sort); do
  out=$(python3 "$f" 2>&1)
  code=$?
  line=$(echo "$out" | grep -E "通过 [0-9]+ / 失败 [0-9]+" | tail -1)
  printf '%-30s exit=%s  %s\n' "$f" "$code" "$(echo "$line" | tr -s ' ')"
  if [ $code -ne 0 ]; then
    echo "$out" | grep -E "^\s+失败" | head -4 | sed 's/^/      /'
  fi
  n=$(echo "$line" | grep -oE "通过 [0-9]+" | grep -oE "[0-9]+")
  total=$((total + ${n:-0}))
done
echo "---- 线上单测合计通过断言：$total"
