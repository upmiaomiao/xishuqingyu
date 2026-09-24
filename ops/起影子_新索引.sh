#!/usr/bin/env bash
# 起影子实例（P6 新索引 + 回填后的语料树），在 8013 上验证；线上 8011 全程不动。
#
# 与 /tmp/起影子.sh 的区别：
#   · 这个额外设 MD_ROOT（语料树）—— 因为这次不只换索引，语料也做了表格回填；
#   · 不做代码替换（P6 的 ingest 改动只影响"建索引"，服务时用的是索引内容）。
#
# 用法：bash /home/test/起影子_新索引.sh [索引目录] [语料树] [端口]
set -u
PY=/home/test/fagui_serve/.venv/bin/python
APP=/home/test/xishu_qingyu_serve/xishu_qingyu_qa.py
IDX=${1:-/data/fagui_rag/index_p6}
MD=${2:-/data/fagui_rag/okf_bundles_p6}
PORT=${3:-8013}
LOG=/tmp/shadow_${PORT}.log

if fuser -n tcp "$PORT" >/dev/null 2>&1; then
  echo "端口 $PORT 被占用，先停掉"
  fuser -k -n tcp "$PORT" 2>/dev/null || true
  sleep 2
fi

echo "启动影子 port=$PORT"
echo "  索引=$IDX"
echo "  语料=$MD"
QA_HOST=127.0.0.1 QA_PORT="$PORT" RAG_INDEX_DIR="$IDX" MD_ROOT="$MD" \
  setsid nohup "$PY" "$APP" > "$LOG" 2>&1 < /dev/null &
echo "  pid=$!  log=$LOG"
sleep 8
echo "--- 健康检查"
curl -fsS "http://127.0.0.1:$PORT/health" || { echo "启动失败，日志尾部："; tail -25 "$LOG"; exit 1; }
echo
echo "--- 索引加载情况"
grep -e Retriever -e chunks -e 索引 "$LOG" | tail -4
