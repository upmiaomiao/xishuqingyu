#!/usr/bin/env bash
# 重建进度：进程是否在跑 + 临时落盘情况
echo "ingest procs: $(pgrep -f ingest_okf | wc -l)"
pgrep -af ingest_okf | head -2
echo "index mtime: $(stat -c %y /data/fagui_rag/index/chunks.jsonl)"
echo "index chunks now: $(wc -l < /data/fagui_rag/index/chunks.jsonl)"
echo "log size: $(stat -c %s /tmp/eia_full.log)"
tail -3 /tmp/eia_full.log
