#!/usr/bin/env bash
# 确认 ingest 是否在活跃工作
echo "== proc =="
ps -o pid=,etime=,time=,rss= -p 3973945 2>/dev/null || echo "(进程不在了)"
echo "== 与嵌入服务的连接 =="
ss -tnp 2>/dev/null | grep 34004 | head -5
echo "连接数: $(ss -tnp 2>/dev/null | grep -c 34004)"
echo "== 嵌入服务健康 =="
curl -fsS -m 10 http://127.0.0.1:34004/v1/models 2>/dev/null | head -c 200 || echo "(无响应)"
echo
echo "== index 目录当前文件 =="
ls -la /data/fagui_rag/index/
echo "== 日志尾 =="
tail -2 /tmp/eia_full.log
