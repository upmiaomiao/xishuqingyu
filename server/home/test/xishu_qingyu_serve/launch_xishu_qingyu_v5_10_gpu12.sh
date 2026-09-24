#!/usr/bin/env bash
# launch_xishu_qingyu_v5_10_gpu12.sh
# 在 10.201.31.10 的 GPU 1,2 上以 TP=2 起 xishu-qingyu-v5。
#
# 为什么用 docker 而不是裸进程：
#   v5 是混合线性注意力架构（64 层里 48 层 linear_attention），vllm 走 GDN 内核，
#   需要 flash-linear-attention / causal_conv1d。本机 wenshu_agent/.venv_serve 只有
#   vllm 0.19.0 且这三个包全部缺失（实测 import 均 MISSING），裸进程起不来。
#   而镜像 vllm/vllm-openai:v0.19.1 已被本机旧容器验证过能跑同架构模型
#   （xishu-qingyu-final，config 同为 Qwen3_5ForConditionalGeneration）。
#
# 数值参数与 .12 上正在跑的那份逐字一致：
#   .12: --served-model-name xishu-qingyu-v5 --tensor-parallel-size 2 --max-num-seqs 64
#        --gpu-memory-utilization 0.90 --dtype bfloat16   （不写 --max-model-len，取模型自带 262144）
# 与旧 launcher(launch_xishu_qingyu_10_gpu23.sh) 的差异：卡号 2,3→1,2，端口 8100→8020，
#   模型路径换成 v5，去掉了 --reasoning-parser qwen3（.12 的 v5 没有它，保持行为一致）。
#
# 前置：GPU 2 必须先释放 —— 旧容器 xishu-qingyu-final-gpu23 带 --restart unless-stopped，
#   必须 docker rm -f，不能只 docker stop。
#
# 用法：sudo bash $0 {start|stop|restart|status|logs}
set -euo pipefail

MODEL_PATH=/data/sft/env_sft/xishu_qingyu_v5_final
IMAGE=vllm/vllm-openai:v0.19.1
CONTAINER=xishu-qingyu-v5-gpu12
PORT=8020
SERVED_NAME=xishu-qingyu-v5
OLD_CONTAINER=xishu-qingyu-final-gpu23

start_service() {
  test -f "$MODEL_PATH/model.safetensors.index.json"   # 权重完整性最低门槛

  # 旧容器占着 GPU 2，且 --restart unless-stopped，只能 rm -f
  if sudo docker ps -a --format '{{.Names}}' | grep -qx "$OLD_CONTAINER"; then
    echo "清理旧容器 $OLD_CONTAINER（占 GPU 2,3）..."
    sudo docker rm -f "$OLD_CONTAINER" >/dev/null
  fi

  sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  sudo docker run -d \
    --name "$CONTAINER" \
    --restart unless-stopped \
    --gpus '"device=1,2"' \
    --ipc=host \
    -v "$MODEL_PATH":/model:ro \
    -p "127.0.0.1:$PORT:8000" \
    "$IMAGE" \
    /model \
    --tensor-parallel-size 2 \
    --served-model-name "$SERVED_NAME" \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 64 \
    --dtype bfloat16 \
    --trust-remote-code
  echo "已启动 container=$CONTAINER gpus=1,2 port=$PORT served=$SERVED_NAME"
}

stop_service() {
  sudo docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  echo "已停止 $CONTAINER"
}

status_service() {
  sudo docker ps -a --filter "name=^/${CONTAINER}$" --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
  echo -n "接口："
  curl -fsS "http://127.0.0.1:$PORT/v1/models" 2>/dev/null | head -c 200 || echo "无响应"
  echo
  nvidia-smi --query-gpu=index,memory.used,memory.total --format=csv,noheader -i 1,2
}

case "${1:-start}" in
  start) start_service ;;
  stop) stop_service ;;
  restart) stop_service; sleep 3; start_service ;;
  status) status_service ;;
  logs) sudo docker logs -f --tail 100 "$CONTAINER" ;;
  *) echo "用法：sudo bash $0 {start|stop|restart|status|logs}" >&2; exit 2 ;;
esac
