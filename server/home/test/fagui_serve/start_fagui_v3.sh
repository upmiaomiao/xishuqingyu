#!/bin/bash
# Phase 3 vLLM 独立服务：Qwen3.6-27B-fagui-v3, port 8100, TP=4, GPU 0-3
export CUDA_VISIBLE_DEVICES=0,1,2,3
export TOKENIZERS_PARALLELISM=false
LOG=/home/test/fagui_serve/vllm_20260620_141711.log
nohup /home/test/fagui_serve/.venv/bin/vllm serve   /data/sft/fagui-sft/export/Qwen3.6-27B-fagui-v3   --host 0.0.0.0 --port 8100   --tensor-parallel-size 4   --max-model-len 8192   --reasoning-parser qwen3   --served-model-name qwen36-fagui-v3   --gpu-memory-utilization 0.85   --trust-remote-code   > $LOG 2>&1 &
echo $! > /home/test/fagui_serve/vllm.pid
echo "PID=$(cat /home/test/fagui_serve/vllm.pid)"
echo "LOG=$LOG"

