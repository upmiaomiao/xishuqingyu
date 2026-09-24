#!/bin/bash
# Phase 3 SFT 模型 vLLM 服务启动脚本
# 模型: Qwen3.6-27B (悉数清宇大模型 · 中节能 phase3 SFT)
# 部署位置: 10.201.31.10 (test 用户, 需要 sudo)
# 端口: 8100  GPU: 0-3  TP=4
#
# 用法:
#   bash launch_fagui_v3.sh         # 启动
#   bash launch_fagui_v3.sh stop    # 停止
#   bash launch_fagui_v3.sh logs    # 看日志
#   bash launch_fagui_v3.sh status  # 看状态

set -e

NAME=fagui-v3
IMAGE=vllm/vllm-openai:v0.19.1
MODEL_PATH=/data/sft/fagui-sft/export/Qwen3.6-27B-fagui-v3
HOST_PORT=8100
# 改成 qwen36-layer2-final 即可被 agent-platform-backend 直接接走
SERVED_NAME=qwen36-fagui-v3
GPUS='"device=0,1,2,3"'
TP=4

case "${1:-start}" in
  start)
    echo "==> 清理旧容器（如存在）"
    sudo docker rm -f "$NAME" 2>/dev/null || true

    echo "==> 启动 $NAME (image=$IMAGE, port=$HOST_PORT, model=$SERVED_NAME)"
    sudo docker run -d \
      --name "$NAME" \
      --restart unless-stopped \
      --gpus "$GPUS" \
      --ipc=host \
      -v "$MODEL_PATH":/model:ro \
      -p "$HOST_PORT":8000 \
      "$IMAGE" \
      /model \
      --tensor-parallel-size "$TP" \
      --max-model-len 8192 \
      --served-model-name "$SERVED_NAME" \
      --gpu-memory-utilization 0.85 \
      --trust-remote-code

    echo
    echo "==> 启动中，27B + TP=4 加载约 3 分钟"
    echo "    watch:  sudo docker logs -f $NAME"
    echo "    test:   curl http://localhost:$HOST_PORT/v1/models"
    echo
    echo "==> 调用示例:"
    cat <<EOF
curl -X POST http://10.201.31.10:$HOST_PORT/v1/chat/completions \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "$SERVED_NAME",
    "messages": [{"role":"user","content":"你是谁？"}],
    "max_tokens": 256,
    "temperature": 0.3
  }'
EOF
    ;;

  stop)
    sudo docker stop "$NAME" && sudo docker rm "$NAME"
    echo "==> 已停止"
    ;;

  logs)
    sudo docker logs -f --tail 100 "$NAME"
    ;;

  status)
    sudo docker ps -a --filter name="$NAME" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
    echo
    echo "==> health check"
    curl -s "http://localhost:$HOST_PORT/v1/models" | head -5 || echo "(服务未响应)"
    ;;

  *)
    echo "用法: $0 {start|stop|logs|status}" >&2
    exit 1
    ;;
esac
