#!/usr/bin/env bash
# 检查重跑结果：进程是否结束、储油库限值表是否入库
S=/data/fagui_rag/okf_bundles_stage
echo "still running: $(pgrep -f 语料正文回填 | wc -l)"
F=$(grep -rl "储油库大气污染物排放标准（GB 20950—2020" "$S" --include=*.md | head -1)
echo "file: $F"
echo "markdown-table separators: $(grep -c -- '| --- |' "$F")"
echo "--- lines mentioning NMHC or 处理效率 ---"
grep -n -e NMHC -e 处理效率 "$F" | tail -8
echo
echo "--- tables (last 24 lines) ---"
tail -24 "$F"
