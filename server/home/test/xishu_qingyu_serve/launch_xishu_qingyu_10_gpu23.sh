#!/usr/bin/env bash
set -euo pipefail

MODEL_PATH=/data/sft/xishu-qingyu/Xishu-Qingyu-Large-Language-Model
IMAGE=vllm/vllm-openai:v0.19.1
CONTAINER=xishu-qingyu-final-gpu23
PORT=8100
SERVED_NAME=xishu-qingyu-final

start_service() {
  test -f "$MODEL_PATH/model.safetensors.index.json"
  sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  sudo docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    --gpus '"device=2,3"' \
    --ipc=host \
    -v "$MODEL_PATH":/model:ro \
    -p "127.0.0.1:$PORT:8000" \
    "$IMAGE" \
    /model \
    --tensor-parallel-size 2 \
    --max-model-len 16384 \
    --served-model-name "$SERVED_NAME" \
    --gpu-memory-utilization 0.82 \
    --reasoning-parser qwen3 \
    --trust-remote-code
  echo "started container=$CONTAINER port=$PORT gpus=2,3"
}

stop_service() {
  sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  echo "stopped"
}

status_service() {
  sudo docker ps -a --filter "name=^/${CONTAINER}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  curl -fsS "http://127.0.0.1:$PORT/v1/models" || true
}

case "${1:-start}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service; start_service ;;
  status) status_service ;;
  logs) sudo docker logs -f --tail 100 "$CONTAINER" ;;
  *) echo "usage: $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
