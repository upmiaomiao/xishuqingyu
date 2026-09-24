#!/usr/bin/env bash
# 只读：找出"检索命中 → 提示词"的那一段（模型到底看得见什么元数据）
set -u
S=/home/test/xishu_qingyu_serve/xishu_pipeline
echo "===== 1) 线上 xishu_pipeline 文件与行数 ====="
wc -l "$S"/*.py | sort -n | tail -20

echo
echo "===== 2) 谁在拼提示词（找「资料」「证据」「来源」这些字样）====="
grep -rn "资料\|参考材料\|以下是检索" "$S"/*.py | grep -v "^.*#" | head -20

echo
echo "===== 3) normalize_sources 的调用点 ====="
grep -rn "normalize_sources" "$S"/*.py | head

echo
echo "===== 4) 提示词模板文件 ====="
ls -l "$S" | head -30
