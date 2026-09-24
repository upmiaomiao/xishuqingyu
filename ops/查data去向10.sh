#!/bin/sh
# 只读：① 查清 /data 从 6.5T 掉到 3.5T 的原因 ② 盘点 /data 可清理项
set -u

echo "########## 第一部分：3TB 去哪了 ##########"

echo "===== 1. /data 现状与 60 秒趋势 ====="
date
df -h /data
a=$(df -k /data | tail -1 | awk '{print $3}')
sleep 60
b=$(df -k /data | tail -1 | awk '{print $3}')
echo "60 秒内已用变化: $(( (b-a)/1024 )) MB"
df -h /data

echo
echo "===== 2. /data 上「已删除但仍被进程占用」的文件（>100M）====="
sudo -n lsof -nP +L1 2>/dev/null | awk '$NF ~ /^\/data/ || $9 ~ /^\/data/ {print}' | head -20
echo "  （空 = 没有）"

echo
echo "===== 3. bash_history 里针对 /data 的删除命令 ====="
for h in /home/test/.bash_history /root/.bash_history; do
  [ -f "$h" ] || continue
  echo "--- $h （最近 40 条含 rm/删除 的）---"
  sudo -n grep -nE 'rm -rf|rm -r |find .* -delete|shred' "$h" 2>/dev/null | grep -i '/data' | tail -20
done
echo "--- 最近 30 条 history（不管内容）---"
sudo -n tail -30 /home/test/.bash_history 2>/dev/null

echo
echo "===== 4. /data/docker 构成（docker data-root）====="
sudo -n du -x -h -d2 /data/docker 2>/dev/null | sort -h | tail -15
echo "--- rootfs/overlayfs 里挂载点数量 ---"
findmnt -rno TARGET 2>/dev/null | grep -c '^/data/docker/rootfs/overlayfs' 

echo
echo "===== 5. /data 下最近 3 天被改动的顶层目录（找异常）====="
sudo -n find /data -xdev -maxdepth 1 -mindepth 1 -mtime -3 -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r

echo
echo "===== 6. /data/sft 各子目录的最后修改时间 ====="
sudo -n find /data/sft -xdev -maxdepth 1 -mindepth 1 -printf '%TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | sort -r

echo
echo
echo "########## 第二部分：/data 可清理项盘点 ##########"

echo "===== 7. /data/sft/qwen3-27b-layer2-sft-v3/tb（943G，/data 最大单项）====="
sudo -n du -x -h -d2 /data/sft/qwen3-27b-layer2-sft-v3/tb 2>/dev/null | sort -h | tail -20
echo "--- tb 下最大的 10 个单文件 ---"
sudo -n find /data/sft/qwen3-27b-layer2-sft-v3/tb -xdev -type f -size +1G -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null \
  | sort -rn | head -10 | awk -F'\t' '{printf "%7.1f GB  %s  %s\n", $1/1073741824, $2, $3}'
echo "--- tb 下 event 文件总量与时间跨度 ---"
sudo -n find /data/sft/qwen3-27b-layer2-sft-v3/tb -xdev -type f -name 'events.out.tfevents*' 2>/dev/null | wc -l
sudo -n find /data/sft/qwen3-27b-layer2-sft-v3/tb -xdev -type f -name 'events.out.tfevents*' -printf '%TY-%Tm-%Td\n' 2>/dev/null | sort | uniq -c | tail -20

echo
echo "===== 8. 优化器状态文件盘点（只在「续训」时才需要，训练结束后是死重量）====="
echo "--- 全部 optim_states.pt ---"
sudo -n find /data -xdev -type f -name '*optim_states.pt' -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null \
  | sort -rn | awk -F'\t' '{printf "%7.1f GB  %s  %s\n", $1/1073741824, $2, $3}'
echo "--- 合计 ---"
sudo -n find /data -xdev -type f -name '*optim_states.pt' -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {printf "%.1f GB, %d 个文件\n", s/1073741824, NR}'
echo "--- 其他训练中间产物 ---"
sudo -n find /data -xdev -type f \( -name '*.pt' -o -name '*.pth' -o -name '*.ckpt' \) -size +5G -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null \
  | sort -rn | head -15 | awk -F'\t' '{printf "%7.1f GB  %s  %s\n", $1/1073741824, $2, $3}'

echo
echo "===== 9. checkpoint 目录逐个大小与时间 ====="
sudo -n find /data/sft -xdev -maxdepth 4 -type d -name 'checkpoint-*' -printf '%TY-%Tm-%Td\t%p\n' 2>/dev/null | sort
echo "--- 逐个 du（可能慢）---"
for d in $(sudo -n find /data/sft -xdev -maxdepth 4 -type d -name 'checkpoint-*' 2>/dev/null); do
  printf '%8s  %s\n' "$(sudo -n du -x -sh "$d" 2>/dev/null | cut -f1)" "$d"
done

echo
echo "===== 10. 大模型权重文件：是否重复（同尺寸同名）====="
sudo -n find /data -xdev -type f -name '*.safetensors' -size +10G -printf '%s\t%i\t%n\t%p\n' 2>/dev/null \
  | sort -rn | awk -F'\t' '{printf "%7.1f GB  inode=%-12s links=%s  %s\n", $1/1073741824, $2, $3, $4}'

echo
echo "===== 11. /data/miaoyonglan（287G）====="
sudo -n du -x -h -d2 /data/miaoyonglan 2>/dev/null | sort -h | tail -12

echo
echo "===== 12. /data/ai-center/model-serving（123G）====="
sudo -n du -x -h -d2 /data/ai-center/model-serving 2>/dev/null | sort -h | tail -12

echo
echo "===== 13. /data/model 与 /data/models ====="
sudo -n du -x -h -d2 /data/model 2>/dev/null | sort -h | tail -12
sudo -n du -x -h -d2 /data/models 2>/dev/null | sort -h | tail -12

echo
echo "===== 14. 缓存与临时类（低风险可清）====="
for d in /data/uv_cache /data/tmp /data/cache /data/vllm_cache /data/docchain /data/miniconda3/pkgs /data/fagui_rag; do
  [ -e "$d" ] && printf '  %-8s %s\n' "$(sudo -n du -x -sh "$d" 2>/dev/null | cut -f1)" "$d"
done

echo
echo "===== 15. conda 环境（44G）====="
sudo -n du -x -h -d1 /data/miniconda3/envs 2>/dev/null | sort -h

echo "===== done ====="
