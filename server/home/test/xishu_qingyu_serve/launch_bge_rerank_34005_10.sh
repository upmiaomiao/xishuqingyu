#!/usr/bin/env bash
# launch_bge_rerank_34005_10.sh
# 在 10.201.31.10 上把 BGE rerank 服务恢复到 34005。
#
# 背景：/data/fagui_rag/retriever.py:15 硬编码
#   BGE_RERANK_URL = "http://127.0.0.1:34005/v1/rerank"
# 且第 60 行发送 "model": "BGE-RERANK-V2-M3"。
# 原容器（跑了 41 天）已消失，34005 无监听；但 retriever.py:87 的兜底
#   except: print("rerank failed, fallback to vec only")
# 会**静默退回纯向量检索**，站点不报错、只是检索质量下降 —— 所以一直没人发现。
#
# 为什么不用 8003 上那个新的 reranker（pid 1592856）：实测它只认模型名 bge-reranker，
# 发 BGE-RERANK-V2-M3 会 404；改指它需要同时改 URL 和模型名两处代码，
# 而且会把站点的检索链挂到别的项目在维护的服务上（该机今天已被 kill 掉 3 个服务）。
#
# 显存：实测同类 reranker 实占约 2.3 GB，这里给 util 0.05（约 4.1 GB 预留）。
#   与 v5 同卡时的预算：v5 util 0.90 = 73.7 GB + embedding 1.9 + rerank 2.3 = 77.9 / 81.92 GB，余 4.0 GB。
#
# 用法：$0 {start|stop|restart|status|logs}
set -euo pipefail

MODEL_PATH=/data/models/modelscope/BAAI/bge-reranker-v2-m3
PY=/home/test/wenshu_agent/.venv_serve/bin/python
SERVED=BGE-RERANK-V2-M3      # 必须与 retriever.py 第 60 行发的名字完全一致
PORT=34005
GPUS=1
BASEDIR=/home/test/xishu_qingyu_serve
LOG=$BASEDIR/vllm_bge_rerank_34005.log
PIDF=$BASEDIR/run_bge_rerank_34005.pid

running() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

start() {
  if running; then echo "已在运行 pid=$(cat "$PIDF")"; return 0; fi
  test -d "$MODEL_PATH"
  cd "$BASEDIR"
  CUDA_VISIBLE_DEVICES=$GPUS nohup "$PY" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --served-model-name "$SERVED" \
    --host 0.0.0.0 --port "$PORT" \
    --max-model-len 4096 \
    --gpu-memory-utilization 0.05 \
    --trust-remote-code \
    > "$LOG" 2>&1 &
  echo $! > "$PIDF"
  echo "已启动 pid=$(cat "$PIDF") gpu=$GPUS port=$PORT served=$SERVED"
}

stop() {
  if running; then kill "$(cat "$PIDF")" 2>/dev/null || true; sleep 5; fi
  pkill -f "api_server --model $MODEL_PATH" 2>/dev/null || true
  rm -f "$PIDF"
  echo "已停止"
}

status() {
  if running; then echo "进程：运行中 pid=$(cat "$PIDF")"; else echo "进程：未运行"; fi
  echo -n "接口："
  curl -fsS "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | head -c 160 || echo "无响应"
  echo
  # 真正的验收：用 retriever.py 完全相同的请求体打一次
  curl -fsS "http://127.0.0.1:$PORT/v1/rerank" \
    -H 'Content-Type: application/json' \
    -d '{"model":"BGE-RERANK-V2-M3","query":"环境影响评价","documents":["环境影响评价法","今天天气不错"]}' \
    2>/dev/null | head -c 200 || echo "rerank 调用失败"
  echo
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 3; start ;;
  status) status ;;
  logs) tail -f "$LOG" ;;
  *) echo "用法：$0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
