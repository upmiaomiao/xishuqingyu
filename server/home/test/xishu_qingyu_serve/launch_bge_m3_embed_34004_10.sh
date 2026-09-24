#!/usr/bin/env bash
# launch_bge_m3_embed_34004_10.sh
# 在 10.201.31.10 上把 BGE-M3 嵌入服务恢复到 34004 —— 这是 P0-1 的修复动作。
#
# 背景：站点 xishu_pipeline/retrieve.py 会 sys.path.insert 到 /data/fagui_rag，
# 那里的 retriever.py 硬编码 BGE_M3_URL = "http://127.0.0.1:34004/v1/embeddings"。
# 34004 原本由 docker 容器 vllm-bge-m3 提供（/data/ai-center/model-serving/bge-m3/docker-compose.yaml），
# 该容器已不在运行，导致任何专业/法规类问题都返回 502「检索服务异常」。
#
# 与 docker-compose.yaml 的对应关系：
#   容器 --model /models/modelscope/BAAI/bge-m3  → 这里 /data/models/modelscope/BAAI/bge-m3（同一份权重，容器内是挂载）
#   容器 --served-model-name BGE-M3              → 一致（retriever 只打 /v1/embeddings，不校验模型名）
#   容器 -p 34004:10001                          → 这里直接 --port 34004
#   容器 --gpu-memory-utilization 0.1            → 这里 0.05（实测 rerank 同类模型只实占 2.3 GB）
#   容器 CUDA_VISIBLE_DEVICES=6                  → 这里改用 GPU 1（v5 起来后两卡合计仍有 12 GB 余量）
# 唯一未复刻的是 compose 里那句 chat-template，/v1/embeddings 用不到它。
set -euo pipefail

MODEL_PATH=/data/models/modelscope/BAAI/bge-m3
PY=/home/test/wenshu_agent/.venv_serve/bin/python
SERVED=BGE-M3
PORT=34004
GPUS=1
BASEDIR=/home/test/xishu_qingyu_serve
LOG=$BASEDIR/vllm_bge_m3_34004.log
PIDF=$BASEDIR/run_bge_m3_34004.pid

running() { [ -f "$PIDF" ] && kill -0 "$(cat "$PIDF")" 2>/dev/null; }

start() {
  if running; then echo "已在运行 pid=$(cat "$PIDF")"; return 0; fi
  test -d "$MODEL_PATH"
  cd "$BASEDIR"
  CUDA_VISIBLE_DEVICES=$GPUS nohup "$PY" -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --served-model-name "$SERVED" \
    --host 0.0.0.0 --port "$PORT" \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.05 \
    --trust-remote-code \
    > "$LOG" 2>&1 &
  echo $! > "$PIDF"
  echo "已启动 pid=$(cat "$PIDF") gpu=$GPUS port=$PORT log=$LOG"
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
  curl -fsS "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | head -c 200 || echo "无响应"
  echo
  # 真正的验收：打一次 embeddings，看维度和 .12/索引一致（1024 维）
  curl -fsS "http://127.0.0.1:$PORT/v1/embeddings" \
    -H 'Content-Type: application/json' \
    -d '{"model":"BGE-M3","input":["环境影响评价"]}' 2>/dev/null \
    | head -c 120 || echo "embeddings 调用失败"
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
