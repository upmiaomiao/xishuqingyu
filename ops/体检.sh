#!/bin/bash
# 两台机器的使用情况体检（.10 应用/语料，.12 模型）
echo "############ $(hostname)  $(date '+%F %T') ############"
echo "--- 负载 / 运行时长 ---"
uptime
echo "CPU 核数：$(nproc)"
echo
echo "--- 内存 ---"
free -h
echo
echo "--- 磁盘（>1G 的挂载点）---"
df -hT -x tmpfs -x devtmpfs -x overlay 2>/dev/null | awk 'NR==1 || $3 ~ /[0-9]G|[0-9]T/'
echo
echo "--- GPU ---"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu \
             --format=csv,noheader 2>/dev/null
  echo "  进程占用："
  nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null | head -8
else
  echo "（无 nvidia-smi）"
fi
echo
echo "--- 吃 CPU 前 6 ---"
ps -eo pcpu,pmem,rss,etime,comm,args --sort=-pcpu 2>/dev/null | head -7 | \
  awk '{printf "  %5s%% cpu  %5s%% mem  %6.1fG  %-10s  %s\n",$1,$2,$3/1048576,$4,substr($0,index($0,$5),70)}'
echo
echo "--- 吃内存前 6 ---"
ps -eo pmem,pcpu,rss,etime,comm,args --sort=-pmem 2>/dev/null | head -7 | \
  awk '{printf "  %5s%% mem  %5s%% cpu  %6.1fG  %-10s  %s\n",$1,$2,$3/1048576,$4,substr($0,index($0,$5),70)}'
echo
echo "--- 关键端口 ---"
for p in 8011 34004 34005 8000 8080 11434 5000 9000 22; do
  owner=$(ss -lntp 2>/dev/null | awk -v P=":$p" '$4 ~ P {print $NF; exit}')
  if [ -n "$owner" ]; then echo "  $p  ${owner:-（无进程信息）}"; fi
done
echo
echo "--- 站点健康 ---"
if curl -s -m 5 -o /dev/null -w "  8011 /health = %{http_code}  用时 %{time_total}s\n" http://127.0.0.1:8011/health; then :; fi
echo
if command -v docker >/dev/null 2>&1; then
  echo "--- docker ---"
  docker ps --format '  {{.Names}}  {{.Status}}  {{.Image}}' 2>/dev/null | head -10
fi
echo
echo "--- /data 里的大户（前 8）---"
if [ -d /data ]; then du -sh /data/* 2>/dev/null | sort -rh | head -8 | sed 's/^/  /'; fi
echo
echo "--- 家目录里的日志大户（前 6）---"
du -ah /home/test 2>/dev/null | sort -rh | grep -E '\.log|\.jsonl|\.npy|\.tar|\.gz' | head -6 | sed 's/^/  /'
