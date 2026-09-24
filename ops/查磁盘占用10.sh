#!/bin/sh
# 只读排查：10.201.31.10 系统盘（/dev/sda2 → /）被什么占满。
# 本脚本不删除任何东西。
set -u

echo "===== 1. containerd / docker / kubelet 状态 ====="
for u in containerd docker kubelet; do
  printf '%-12s active=%s enabled=%s\n' "$u" "$(systemctl is-active $u 2>&1)" "$(systemctl is-enabled $u 2>&1)"
done

echo
echo "===== 2. containerd 命名空间 ====="
sudo -n ctr namespace ls 2>&1

echo
echo "===== 3. 各命名空间的容器（含停止的）====="
for ns in k8s.io default moby; do
  echo "--- ns=$ns containers ---"
  sudo -n ctr -n "$ns" containers ls 2>&1 | head -30
done

echo
echo "===== 4. 各命名空间镜像数量与列表（前 40）====="
for ns in k8s.io default moby; do
  echo "--- ns=$ns images ---"
  sudo -n ctr -n "$ns" images ls 2>&1 | head -40
  echo "    count: $(sudo -n ctr -n "$ns" images ls -q 2>/dev/null | wc -l)"
done

echo
echo "===== 5. docker 视角 ====="
sudo -n docker ps -a 2>&1 | head -20
echo "--- docker images ---"
sudo -n docker images 2>&1 | head -30
echo "--- docker system df ---"
sudo -n docker system df -v 2>&1 | head -30

echo
echo "===== 6. k8s 视角（如果有）====="
sudo -n kubectl get nodes 2>&1 | head -5
sudo -n kubectl get pods -A 2>&1 | head -30
sudo -n crictl ps -a 2>&1 | head -20

echo
echo "===== 7. containerd 数据库里的对象计数 ====="
D=/var/lib/containerd/io.containerd.metadata.v1.bolt
sudo -n ls -la "$D" 2>&1 | head -5

echo
echo "===== 8. snapshots 目录：数量 / 按 inode 时间分布 ====="
S=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots
echo "snapshot 个数: $(sudo -n ls -1 $S 2>/dev/null | wc -l)"
echo "--- 最近修改时间分布（按月）---"
sudo -n find $S -maxdepth 1 -mindepth 1 -printf '%TY-%Tm\n' 2>/dev/null | sort | uniq -c

echo
echo "===== 9. 真正在跑的容器进程 ====="
ps -eo pid,user,etime,rss,args --sort=-rss 2>/dev/null | grep -E 'containerd-shim|vllm|nginx|uvicorn|gunicorn' | grep -v grep | head -20

echo
echo "===== 10. 已删除但仍被占用的文件（>100M）====="
sudo -n lsof -nP +L1 2>/dev/null | awk '$7 > 104857600 {print $1, $2, $7, $9}' | head -20

echo
echo "===== 11. /root 占用 ====="
sudo -n du -x -h -d1 /root 2>/dev/null | sort -h | tail -15

echo
echo "===== 12. 服务相关目录（不可删）确认 ====="
for d in /home/test/xishu_qingyu_serve /home/test/fagui_serve /home/test/wenshu_agent /home/test/projects /home/test/agent_platform; do
  printf '%-40s %s\n' "$d" "$(du -x -sh $d 2>/dev/null | cut -f1)"
done

echo
echo "===== 13. 监听端口（在跑的服务）====="
sudo -n ss -lntp 2>/dev/null | cut -c1-150 | head -25

echo "===== done ====="
