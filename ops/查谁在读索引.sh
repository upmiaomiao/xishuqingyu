#!/bin/bash
# 换索引前安全检查：谁在读 /data/fagui_rag/index
set -u
echo "===== 1) 引用了 fagui_rag/index 的服务端文件 ====="
for d in /data/eia_audit /data/eia_report_gen /home/test/xishu_qingyu_serve /data/fagui_rag; do
  echo "--- $d ---"
  grep -rIl --exclude-dir=.git --exclude-dir=node_modules --exclude='*.log' \
       -e "fagui_rag/index" -e "INDEX_DIR" "$d" 2>/dev/null | head -20
done

echo
echo "===== 2) 正在跑的相关进程 ====="
ps -eo pid,etime,cmd | grep -E "uvicorn|python" | grep -v grep | head -20

echo
echo "===== 3) 三个服务的端口与健康 ====="
for p in 8011 8012 8013 8021 8031; do
  c=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "http://127.0.0.1:$p/health" 2>/dev/null || echo "-")
  printf "  :%s -> %s\n" "$p" "$c"
done
echo
echo "===== 4) /data/fagui_rag 目录现状 ====="
ls -la /data/fagui_rag/ | head -20
echo "--- index 大小 ---"
du -sh /data/fagui_rag/index 2>/dev/null
