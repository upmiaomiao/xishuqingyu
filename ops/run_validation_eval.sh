#!/bin/bash
# Run evaluation on validation_eval.jsonl
# Usage: ./run_validation_eval.sh [TAG] [LIMIT] [CONCURRENCY]

TAG=${1:-validation}
LIMIT=${2:-}
CONCURRENCY=${3:-4}

cd /home/test/wenshu_agent

# Activate virtual environment
source .venv/bin/activate

# Set environment variables for services
export VLLM_BASE_URL=http://localhost:8000/v1
export VLLM_MODEL=qwen36-layer2-final
export XIYAN_BASE_URL=http://localhost:8002/v1
export XIYAN_MODEL=xiyan-7b
export EMB_BASE_URL=http://localhost:8001/v1
export EMB_MODEL=bge-zh-emb
export EMB_QUERY_FORMAT="{query}"
export EMB_VECTORS_PATH=/home/test/wenshu_agent/code/index/table_vectors_bge_zh_sft_v3.npy
export EMB_META_PATH=/home/test/wenshu_agent/code/index/table_meta_bge_zh_sft_v3.json

# Build command
CMD="python3 code/eval_e2e_agent.py --in data/final/validation_eval.jsonl --tag $TAG --concurrency $CONCURRENCY"
if [ -n "$LIMIT" ]; then
    CMD="$CMD --limit $LIMIT"
fi

echo "Running: $CMD"
$CMD
