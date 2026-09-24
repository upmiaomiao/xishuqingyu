#!/bin/sh
# 清理后健康核查（只读）
set -u

echo "===== 1. 系统盘 ====="
df -h /

echo
echo "===== 2. 运行中的容器数 ====="
echo "running: $(sudo -n docker ps -q 2>/dev/null | wc -l)    all: $(sudo -n docker ps -aq 2>/dev/null | wc -l)"

echo
echo "===== 3. 关键服务端口探测（HTTP 状态码）====="
for p in 8011 8010 8000 8001 8002 8080 18000 38080 38081 28080 33001 35004 35005 6006; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:$p/" 2>/dev/null)
  printf '  port %-6s -> %s\n' "$p" "${code:-无响应}"
done

echo
echo "===== 4. 生产站点 8011 健康检查 ====="
curl -s --max-time 10 http://127.0.0.1:8011/health 2>&1 | head -5
echo
echo "--- 8011 进程 ---"
ps -o pid,etime,args -p "$(sudo -n ss -lntp 2>/dev/null | grep ':8011' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)" 2>&1 | tail -2

echo
echo "===== 5. vLLM 容器状态 ====="
sudo -n docker ps --format '{{.Names}}|{{.Status}}' 2>&1 | grep -i vllm

echo
echo "===== 6. docker 空间现状 ====="
sudo -n docker system df 2>&1
echo "--- buildx ---"
sudo -n docker buildx du 2>/dev/null | tail -3

echo
echo "===== 7. containerd / 各目录现状 ====="
sudo -n du -x -sh /var/lib/containerd 2>/dev/null
du -x -h -d1 / 2>/dev/null | sort -h | tail -8

echo
echo "===== 8. inode ====="
df -i / | tail -1

echo
echo "===== 9. 最近 15 分钟有无容器重启 ====="
sudo -n docker ps --format '{{.Names}}|{{.Status}}' 2>&1 | grep -iE 'second|minute|Less than' | head -10
echo "(以上为空说明没有容器在清理后重启)"

echo "===== done ====="
