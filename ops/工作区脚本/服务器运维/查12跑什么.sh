#!/bin/bash
# .12 这台机子上到底跑着什么
echo "################ .12 运行清单  $(date '+%F %T') ################"
echo
echo "=== 1. 谁在用这台机器（按用户统计进程数/内存）==="
ps -eo user= | sort | uniq -c | sort -rn | head -12 | sed 's/^/  /'
echo
echo "=== 2. 所有监听端口（含进程）==="
ss -lntp 2>/dev/null | awk 'NR>1{printf "  %-22s %s\n",$4,$6}' | sort -u | head -40
echo "  —— UDP ——"
ss -lnup 2>/dev/null | awk 'NR>1{printf "  %-22s %s\n",$4,$6}' | sort -u | head -12
echo
echo "=== 3. Docker 容器（全部）==="
docker ps --format '  {{.Names}}｜{{.Status}}｜{{.Ports}}' 2>/dev/null
echo
echo "=== 4. GPU 占用（按卡汇总 + 进程归属）==="
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader | sed 's/^/  /'
echo "  —— 计算进程（pid → 命令）——"
nvidia-smi --query-compute-apps=pid,used_memory,process_name --format=csv,noheader | while IFS=, read -r pid mem name; do
  pid=$(echo $pid | tr -d ' ')
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-110)
  owner=$(ps -o user= -p $pid 2>/dev/null)
  printf "  pid=%-8s %-10s %-12s %s\n" "$pid" "$mem" "${owner:-?}" "${cmd:-$name}"
done
echo
echo "=== 5. python / vllm / 训练进程（按内存排序，前 20）==="
ps -eo pid,user,etime,rss,pcpu,args --sort=-rss 2>/dev/null | grep -E 'python|vllm|node|java|ollama' | grep -v grep | head -20 | \
  awk '{printf "  pid=%-8s %-9s 跑=%-13s 内存=%.1fG cpu=%s%%  %s\n",$1,$2,$3,$4/1048576,$5,substr($0,index($0,$6),86)}'
echo
echo "=== 6. 会话（tmux / screen / 登录）==="
if command -v tmux >/dev/null 2>&1; then tmux ls 2>/dev/null | sed 's/^/  tmux: /'; fi
screen -ls 2>/dev/null | head -6 | sed 's/^/  screen: /'
who 2>/dev/null | sed 's/^/  /'
echo
echo "=== 7. 开机自启 / 计划任务 ==="
systemctl list-units --type=service --state=running 2>/dev/null | grep -vE 'systemd|dbus|polkit|getty|journald|udev|ssh\.|cron\.|rsyslog|NetworkManager|chronyd|irqbalance|auditd|firewalld|tuned|abrt|gssproxy|sssd|postfix|crond' | head -12 | sed 's/^/  /'
echo "  —— crontab ——"
for u in root test; do echo "  [$u]"; crontab -u $u -l 2>/dev/null | grep -v '^#' | head -6 | sed 's/^/    /'; done
echo
echo "=== 8. 最近登录过的人 / 常用工作目录 ==="
last -n 8 2>/dev/null | head -8 | sed 's/^/  /'
echo
echo "=== 9. 各人 /data 目录的最近改动时间 ==="
for d in /data/*/; do
  t=$(stat -c %y "$d" 2>/dev/null | cut -c1-16)
  s=$(du -sh "$d" 2>/dev/null | cut -f1)
  printf "  %-28s %-8s 改动 %s\n" "$d" "$s" "$t"
done
echo
echo "=== 10. 负载来源：近 1 分钟最忙的进程 ==="
ps -eo pcpu,pid,user,etime,comm --sort=-pcpu 2>/dev/null | head -9 | sed 's/^/  /'
