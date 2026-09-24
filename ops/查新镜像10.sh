#!/bin/sh
# 查清 llmdoc-ocr-vl-gpu 这个新镜像从哪来、是否正在被部署
set -u

echo "===== 1. 该镜像详情 ====="
sudo -n docker images --format '{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Size}}|{{.CreatedAt}}|{{.CreatedSince}}' 2>&1 \
  | grep -i llmdoc

echo
echo "===== 2. 镜像内部时间戳（确认构建时间）====="
sudo -n docker inspect llmdoc-ocr-vl-gpu:C_202608311500 \
  --format 'Created={{.Created}}  Id={{.Id}}' 2>&1 | head -3

echo
echo "===== 3. 是否有容器引用它（含已停止）====="
sudo -n docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}|{{.CreatedAt}}' 2>&1 | grep -i llmdoc
echo "  （空 = 没有容器引用）"

echo
echo "===== 4. 最近 2 小时有新容器被创建吗 ====="
sudo -n docker ps -a --format '{{.CreatedAt}}|{{.Names}}|{{.Image}}|{{.Status}}' 2>&1 | sort -r | head -10

echo
echo "===== 5. 现在所有镜像（按大小）====="
sudo -n docker images --format '{{.Size}}|{{.Repository}}:{{.Tag}}|{{.CreatedSince}}' 2>&1 | sort -hr | head -12
echo "  镜像总数: $(sudo -n docker images -q 2>/dev/null | sort -u | wc -l)"

echo
echo "===== 6. docker system df ====="
sudo -n docker system df 2>&1

echo
echo "===== 7. 当前系统盘 ====="
df -h /

echo
echo "===== 8. 是否有正在进行的 docker pull / build ====="
ps -eo pid,user,etime,args 2>/dev/null | grep -E 'docker (pull|build|compose|run)|buildkit' | grep -v grep | head -10
echo "  （空 = 没有正在进行的拉取/构建）"

echo
echo "===== 9. 登录用户（谁可能刚操作了）====="
who 2>&1 | head -10

echo
echo "===== 10. docker 事件流最近记录 ====="
sudo -n timeout 5 docker events --since 2h --until 0s \
  --filter type=image --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' 2>&1 | tail -15

echo "===== done ====="
