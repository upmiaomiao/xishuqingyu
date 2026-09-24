#!/bin/bash
# Launch fagui v3 (Qwen3.6-27B) on GPU 6,7 with TP=2 using env_sci vLLM 0.19.1
set -e

# Kill any existing fagui v3 process
pkill -f "fagui-v3" 2>/dev/null || true
pkill -f "port 8100" 2>/dev/null || true
sleep 2

MODEL=/data/sft/fagui-sft/export/Qwen3.6-27B-fagui-v3
VLLM=/data/miniconda3/envs/env_sci/bin/vllm
LOG=/home/test/fagui_serve/vllm_fagui_v3_gpu67.log

export CUDA_VISIBLE_DEVICES=6,7
export TOKENIZERS_PARALLELISM=false

nohup $VLLM serve $MODEL \
  --host 0.0.0.0 \
  --port 8100 \
  --tensor-parallel-size 2 \
  --max-model-len 8192 \
  --reasoning-parser qwen3 \
  --served-model-name qwen36-fagui-v3 \
  --gpu-memory-utilization 0.70 \
  --trust-remote-code \
  > $LOG 2>&1 &

echo "fagui v3 launched on GPU 6,7 port 8100, PID $!"
echo "Log: $LOG"
