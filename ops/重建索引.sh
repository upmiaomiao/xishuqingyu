#!/bin/bash
# 重建索引到新目录（不动线上 /data/fagui_rag/index）
#   用法：bash 重建索引.sh dry     —— 只切块，报数量（零成本预演）
#         bash 重建索引.sh full    —— 真跑 embedding，落盘到 index_v3
set -e
PY=/home/test/fagui_serve/.venv/bin/python
SRC=/home/test/fagui_serve/../../../data/fagui_rag/ingest_okf.py
ING=/data/fagui_rag/ingest_okf.py
export BUNDLE_ROOT=/data/fagui_rag/okf_bundles
export INDEX_DIR=/data/fagui_rag/index_v3
MODE=${1:-dry}

echo "语料根：$BUNDLE_ROOT"
echo "输出目录：$INDEX_DIR"
echo "线上索引 chunk 数：$(wc -l < /data/fagui_rag/index/chunks.jsonl)"

if [ "$MODE" = "dry" ]; then
  "$PY" "$ING" --dry-run 2>&1 | tail -25
  exit 0
fi

echo
echo "===== 全量 embedding 开始 $(date '+%H:%M:%S') ====="
nohup "$PY" "$ING" > /home/test/重建index_v3.log 2>&1 &
echo "已在后台启动，pid=$!"
echo "日志：/home/test/重建index_v3.log"
