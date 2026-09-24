#!/usr/bin/env bash
# 检查关键文档的暂存版本里到底有没有限值表
S=/data/fagui_rag/okf_bundles_stage
echo "==== 储油库：含 NMHC 的行"
grep -rl "储油库大气污染物排放标准（GB 20950—2020" "$S" --include=*.md | while read -r f; do
  echo "--- $f"
  grep -n -e "NMHC" -e "处理效率" -e "≤25" "$f" | head -8
  echo "  含表格分隔行 |---| 的行数: $(grep -c -- '| --- |' "$f")"
done
echo
echo "==== 制糖：表格还原情况"
grep -rl "制糖工业水污染物排放标准（GB 21909-2008" "$S" --include=*.md | while read -r f; do
  echo "--- $(basename "$f")  表格行数: $(grep -c -- '| --- |' "$f")"
done
