#!/bin/sh
# 只读：补查 /data 的三处关键细节
set -u

echo "===== 1. 801G 的 RL 产物构成 ====="
sudo -n du -x -h -d2 /data/sft/qwen3-27b-layer2-sft-v3/tb/cost_aware/rl_out 2>/dev/null | sort -h | tail -20
echo "--- rl_out 下 checkpoint 步数统计 ---"
sudo -n find /data/sft/qwen3-27b-layer2-sft-v3/tb/cost_aware/rl_out -xdev -maxdepth 2 -mindepth 2 -type d 2>/dev/null | wc -l
echo "--- 各实验目录 ---"
sudo -n du -x -h -d1 /data/sft/qwen3-27b-layer2-sft-v3/tb/cost_aware/rl_out 2>/dev/null | sort -h | tail -15

echo
echo "===== 2. 有没有训练任务在跑（决定 optim_states 能不能删）====="
ps -eo pid,user,etime,args 2>/dev/null | grep -iE 'torchrun|deepspeed|llamafactory|accelerate|train\.py|verl|ray::' | grep -v grep | head -15
echo "  （空 = 没有训练在跑）"
echo "--- GPU 占用 ---"
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv 2>/dev/null | head -20

echo
echo "===== 3. 09:16 被改动的三个目录，现在还剩下什么 ====="
for d in /data/sft/xiyan14b_v1_full_sft /data/sft/qwen36-27b-layer2-sft-v1-8gpu /data/sft/qwen36-27b-layer2-hard-sft-v1; do
  echo "--- $d ---"
  sudo -n ls -la --time-style=long-iso "$d" 2>/dev/null | head -15
done

echo
echo "===== 4. /data 上是否还有别的训练产物的 mtime 集中在 09:15-09:30 ====="
sudo -n find /data -xdev -maxdepth 3 -type d -newermt '2026-09-21 09:10' ! -newermt '2026-09-21 09:40' -printf '%TH:%TM  %p\n' 2>/dev/null | sort | head -30

echo
echo "===== 5. /data/sft 下所有 >5G 的目录（可清理候选全景）====="
sudo -n du -x -h -d3 /data/sft 2>/dev/null | awk '$1 ~ /[0-9.]+G|T/' | sort -h | tail -30

echo
echo "===== 6. fagui-sft 内部构成（205G）====="
sudo -n du -x -h -d2 /data/sft/fagui-sft 2>/dev/null | sort -h | tail -12

echo
echo "===== 7. 各 checkpoint 目录的纯净度：能否只删优化器状态、保留模型权重 ====="
for d in /data/sft/xiyan7b_v4_full_sft/checkpoint-100 \
         /data/sft/xiyan7b_v4_full_sft/checkpoint-200 \
         /data/sft/xiyan7b_v4_full_sft/checkpoint-242 \
         /data/sft/xiyan14b_v2_full_sft/checkpoint-375 \
         /data/sft/fagui-sft/output/checkpoint-208 \
         /data/sft/fagui-sft/output_phase2/checkpoint-4; do
  echo "--- $d ---"
  sudo -n du -x -h -d1 "$d" 2>/dev/null | sort -h | tail -8
done

echo
echo "===== 8. 引用检查：这些 checkpoint 有没有被脚本/配置引用（避免删了断链）====="
sudo -n grep -rl 'checkpoint-100\|checkpoint-200\|checkpoint-242\|checkpoint-375' \
  /home/test/xishu_qingyu_serve /home/test/wenshu_agent /home/test/fagui_serve \
  /data/sft/script /data/fagui_rag --include='*.py' --include='*.sh' --include='*.json' --include='*.yaml' --include='*.env' 2>/dev/null | head -20
echo "  （空 = 没有脚本引用）"

echo "===== done ====="
