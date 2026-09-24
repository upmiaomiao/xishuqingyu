#!/usr/bin/env bash
# 打印储油库暂存文件里限值表附近的原文行
S=/data/fagui_rag/okf_bundles_stage
F=$(grep -rl "储油库大气污染物排放标准（GB 20950—2020" "$S" --include=*.md | head -1)
echo "file: $(basename "$F")  总行数: $(wc -l < "$F")"
echo "--- 236~254 行 ---"
sed -n '236,254p' "$F"
echo
echo "--- 全文里独立出现的 95 / 25 ---"
grep -n -E '(^|[^0-9])95([^0-9]|$)' "$F" | head -6
echo
echo "--- 附：段落 / 表格 段落标题 ---"
grep -n "附：" "$F"
