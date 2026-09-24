#!/bin/sh
# 只读排查第三轮：精确核对「镜像↔容器」归属，定出真正没人用的镜像。
# 本脚本只统计，不删除任何东西。
set -u

echo "===== A. 全部容器（含已停止）====="
sudo -n docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>&1 | sort -t'|' -k3

echo
echo "===== B. 容器使用的镜像引用（去重计数）====="
sudo -n docker ps -a --format '{{.Image}}' 2>&1 | sort | uniq -c | sort -rn

echo
echo "===== C. 镜像清单（镜像ID 去重，标注是否被任何容器引用）====="
sudo -n docker ps -a --format '{{.Image}}' 2>&1 | sort -u > /tmp/_used.txt
sudo -n docker images --format '{{.ID}}|{{.Repository}}:{{.Tag}}|{{.Size}}|{{.CreatedSince}}' 2>&1 | while IFS='|' read -r id repo size created; do
  hit=$(grep -F -c "$repo" /tmp/_used.txt 2>/dev/null)
  [ "$hit" -gt 0 ] && mark="使用中" || mark="未使用"
  printf '%s|%-60s|%-10s|%-16s|%s\n' "$mark" "$repo" "$size" "$created" "$id"
done | sort

echo
echo "===== D. 按镜像ID 聚合：同一 ID 多标签（不重复占空间）====="
sudo -n docker images --format '{{.ID}}' 2>&1 | sort | uniq -c | sort -rn | head -10

echo
echo "===== E. 构建缓存汇总（reclaimable 明细）====="
sudo -n docker buildx du 2>&1 | tail -4
echo "--- 可回收记录条数与体积 ---"
sudo -n docker buildx du --verbose 2>&1 | awk '$2=="true"{n++; print $3}' | tail -0
sudo -n docker buildx du --verbose 2>&1 | awk '$2=="true"' | wc -l
sudo -n docker buildx du --verbose 2>&1 | head -3

echo
echo "===== F. /data 用量与构成（次生问题）====="
df -h /data | tail -1
sudo -n du -x -h -d1 /data 2>/dev/null | sort -h | tail -15
echo "--- /data/docker（docker data-root）---"
sudo -n du -x -sh /data/docker 2>/dev/null

echo
echo "===== G. huggingface datasets 缓存明细 ====="
du -sh /home/test/.cache/huggingface/datasets/* 2>/dev/null | sort -hr | head -20

echo
echo "===== H. /root/.cache 明细 ====="
sudo -n bash -c 'du -sh /root/.cache/* 2>/dev/null | sort -hr | head -10'

echo
echo "===== I. /home/test/wenshu_agent 与 fagui_serve 构成 ====="
du -x -h -d1 /home/test/wenshu_agent 2>/dev/null | sort -h | tail -8
echo "---"
du -x -h -d1 /home/test/fagui_serve 2>/dev/null | sort -h | tail -8

echo
echo "===== J. /home/test/projects 构成 ====="
du -x -h -d1 /home/test/projects 2>/dev/null | sort -h | tail -12

echo
echo "===== K. docker 卷 ====="
sudo -n docker volume ls -f dangling=true 2>&1 | head -10
echo "volumes 总数: $(sudo -n docker volume ls -q 2>&1 | wc -l)"

echo "===== done ====="
