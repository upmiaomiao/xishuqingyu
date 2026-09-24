#!/usr/bin/env bash
# 影子实例：用暂存索引在 8012 起一份，验证通过后再切正式 8011。
# 线上 8011 全程不动。
set -u
PY=/home/test/fagui_serve/.venv/bin/python
APP=/home/test/xishu_qingyu_serve/xishu_qingyu_qa.py
STAGE_INDEX=${1:-/data/fagui_rag/index_stage}
PORT=${2:-8012}
LOG=/tmp/shadow_${PORT}.log

if fuser -n tcp "$PORT" >/dev/null 2>&1; then
  echo "端口 $PORT 已被占用，先停掉："
  fuser -k -n tcp "$PORT" 2>/dev/null || true
  sleep 2
fi

echo "启动影子实例 port=$PORT index=$STAGE_INDEX"
QA_HOST=127.0.0.1 QA_PORT="$PORT" RAG_INDEX_DIR="$STAGE_INDEX" \
  setsid nohup "$PY" "$APP" > "$LOG" 2>&1 < /dev/null &
echo "pid=$!  log=$LOG"
sleep 6
echo "--- 健康检查"
curl -fsS "http://127.0.0.1:$PORT/health" || { echo "启动失败，日志："; tail -20 "$LOG"; exit 1; }
echo
echo "--- 索引加载日志"
grep -e Retriever -e chunks "$LOG" | tail -3
