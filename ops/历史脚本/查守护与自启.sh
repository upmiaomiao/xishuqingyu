#!/bin/bash
echo "=== 1. v5 容器状态与重启策略 ==="
sudo -S docker ps -a --filter name=xishu-qingyu-v5 --format '{{.Names}} | {{.Status}} | {{.Image}}' <<< "Cecepd@123456" 2>/dev/null
echo "--- 重启策略 ---"
sudo -S docker inspect xishu-qingyu-v5-gpu12 --format '{{.HostConfig.RestartPolicy.Name}} | privileged={{.HostConfig.Privileged}} | gpus={{.HostConfig.DeviceRequests}}' <<< "Cecepd@123456" 2>/dev/null

echo
echo "=== 2. 站点进程是否有守护（systemd / supervisor）==="
systemctl list-units --type=service --all 2>/dev/null | grep -iE 'xishu|fagui|8011' || echo "  systemd 中无相关 unit"
ls /etc/supervisor/conf.d/ 2>/dev/null || echo "  无 supervisor"

echo
echo "=== 3. 开机自启 / 定时任务 ==="
crontab -l 2>/dev/null | grep -vE '^#' | grep -v '^$' || echo "  crontab 为空"

echo
echo "=== 4. 三个服务的启动方式（是否 nohup 裸进程）==="
ps -eo pid,ppid,etime,cmd | grep -E '[b]ge-m3 --served|[b]ge-reranker-v2-m3 --served|[x]ishu_qingyu_qa.py'

echo
echo "=== 5. 站点 8011 的启动命令与父进程 ==="
ps -o pid,ppid,etime,cmd -p 2194863
echo "--- 父进程 ---"
ps -o pid,cmd -p $(ps -o ppid= -p 2194863 | tr -d ' ') 2>/dev/null

echo
echo "=== 6. 是否有 nginx / 反向代理在前 ==="
ps -eo pid,cmd | grep -E '[n]ginx|[c]addy|[t]raefik' | head -5 || echo "  无反向代理"
ss -ltn 2>/dev/null | grep -E ':(80|443) ' || echo "  80/443 未监听"

echo
echo "=== 7. 防火墙 ==="
sudo -S iptables -L INPUT -n 2>/dev/null | head -10 <<< "Cecepd@123456"

echo
echo "=== 8. 服务启动时间线 ==="
echo "站点 8011 : $(ps -o lstart= -p 2194863)"
echo "embedding : $(ps -o lstart= -p 2090235)"
echo "rerank    : $(ps -o lstart= -p 2128352)"
echo "v5 容器   : $(sudo -S docker inspect xishu-qingyu-v5-gpu12 --format '{{.State.StartedAt}}' <<< "Cecepd@123456" 2>/dev/null)"
