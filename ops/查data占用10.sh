#!/bin/sh
# 只读排查：/data（7.0T，98% 满）被什么占满。
# 本脚本不删除任何东西。
set -u

echo "===== 1. 挂载与用量 ====="
df -h /data
df -i /data | tail -1
echo "--- 是否有嵌套挂载（排除后才是真实占用）---"
findmnt -rno TARGET,SOURCE,FSTYPE 2>/dev/null | grep -E '^/data' | head -20
echo "--- 顶层目录（du -x -d1）---"
sudo -n du -x -h -d1 /data 2>/dev/null | sort -h

echo
echo "===== 2. /data/sft 二层（5.4T 大头）====="
sudo -n du -x -h -d2 /data/sft 2>/dev/null | sort -h | tail -40

echo
echo "===== 3. /data/sft 三个最大的子目录再展开一层 ====="
for d in $(sudo -n du -x -h -d1 /data/sft 2>/dev/null | sort -h | tail -3 | awk '{print $2}'); do
  echo "--- $d ---"
  sudo -n du -x -h -d1 "$d" 2>/dev/null | sort -h | tail -12
done

echo
echo "===== 4. /data/model 与 /data/models（名字像，别搞混）====="
echo "--- /data/model (267G) ---"
sudo -n du -x -h -d1 /data/model 2>/dev/null | sort -h | tail -15
echo "--- /data/models (99G) ---"
sudo -n du -x -h -d1 /data/models 2>/dev/null | sort -h | tail -15

echo
echo "===== 5. 其他大目录二层 ====="
for d in /data/miaoyonglan /data/ai-center /data/env_sci /data/miniconda3 /data/docchain /data/uv_cache /data/vllm019 /data/embedding_ft /data/sensevoice /data/fagui_rag /data/chenz; do
  echo "--- $d ---"
  sudo -n du -x -h -d1 "$d" 2>/dev/null | sort -h | tail -8
done

echo
echo "===== 6. /data 下最大的 25 个目录（深度 3）====="
sudo -n du -x -h -d3 /data 2>/dev/null | sort -h | tail -25

echo
echo "===== 7. /data 下最大的 20 个单文件 ====="
sudo -n find /data -xdev -type f -size +2G -printf '%s\t%TY-%Tm-%Td\t%p\n' 2>/dev/null \
  | sort -rn | head -20 \
  | awk -F'\t' '{printf "%6.1f GB  %s  %s\n", $1/1073741824, $2, $3}'

echo
echo "===== 8. checkpoint 类目录统计（训练产物，最常见的可清理项）====="
echo "--- /data/sft 下 checkpoint-* 目录数 ---"
sudo -n find /data/sft -xdev -maxdepth 4 -type d -name 'checkpoint-*' 2>/dev/null | wc -l
echo "--- 各训练目录的 checkpoint 数量（按数量降序）---"
sudo -n find /data/sft -xdev -maxdepth 3 -type d -name 'checkpoint-*' 2>/dev/null \
  | sed 's#/checkpoint-[0-9]*$##' | sort | uniq -c | sort -rn | head -25

echo
echo "===== 9. 正在被进程使用的 /data 路径（不可删）====="
ps -eo args 2>/dev/null | grep -oE '/data/[A-Za-z0-9_./-]+' | sort -u | head -40

echo
echo "===== 10. 正在被容器挂载的 /data 路径（不可删）====="
for c in $(sudo -n docker ps -aq 2>/dev/null); do
  sudo -n docker inspect "$c" --format '{{$n:=.Name}}{{range .Mounts}}{{.Source}}|{{.Destination}}|{{$n}}{{"\n"}}{{end}}' 2>/dev/null
done | grep '^/data' | sort -u | head -40

echo
echo "===== 11. 最近 30 天有写入的大目录（说明还在用）====="
sudo -n find /data -xdev -maxdepth 2 -type d -mtime -30 -printf '%TY-%Tm-%Td  %p\n' 2>/dev/null | sort -r | head -25

echo
echo "===== 12. 回收站 / 临时 / 下载残留 ====="
for d in /data/.Trash /data/Trash /data/lost+found /data/tmp /data/temp /data/downloads /data/.cache /data/uv_cache; do
  [ -e "$d" ] && printf '  %-8s %s\n' "$(sudo -n du -x -sh "$d" 2>/dev/null | cut -f1)" "$d"
done

echo "===== done ====="
