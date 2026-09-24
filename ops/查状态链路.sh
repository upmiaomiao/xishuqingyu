#!/usr/bin/env bash
# 只读：状态标记这条链路（索引 status → 检索降权 → 模型看到的上下文）
set -u
S=/home/test/xishu_qingyu_serve/xishu_pipeline
echo "===== 1) 降权与判定 ====="
grep -n "ABOLISH\|abolish\|废止" "$S/retrieve.py" | head -20

echo
echo "===== 2) 上下文里怎么带状态（第 15-40 行）====="
sed -n '15,40p' "$S/retrieve.py"

echo
echo "===== 3) 状态字段被谁用（全库找『现行状态』）====="
grep -rn "现行状态\|validity_status" "$S/"*.py "$S/../frontend/js/"*.js 2>/dev/null | head -12

echo
echo "===== 4) 提示词里有没有交代状态 ====="
grep -rn "废止\|现行" "$S/prompts.py" "$S/understand.py" 2>/dev/null | head -12
