#!/usr/bin/env bash
# 内存与 OOM 检查 + 单次检索探针（不过滤输出）
echo "== 内存 =="
free -g
echo
echo "== 各进程 RSS (GB) =="
ps -eo pid=,rss=,etime=,cmd= --sort=-rss | head -8 | awk '{printf "%-8s %6.2f GB  %-10s %s\n", $1, $2/1048576, $3, substr($0, index($0,$4), 60)}'
echo
echo "== 最近 OOM =="
(dmesg 2>/dev/null | grep -i -e 'killed process' -e 'out of memory' | tail -5) || echo "(dmesg 不可读)"
journalctl -k --since "-2h" 2>/dev/null | grep -i -e 'killed process' -e 'oom' | tail -5 || true
echo
echo "== 单次检索探针（完整输出）=="
timeout 300 /home/test/fagui_serve/.venv/bin/python /tmp/查检索结果.py "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？" --top-k 2 2>&1 | head -14
echo "退出码: $?"
