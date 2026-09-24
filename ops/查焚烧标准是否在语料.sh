#!/bin/bash
# 核实：垃圾焚烧核心标准 GB 18485（及 GB 18484）到底在不在语料/索引里
echo "===== 1) 索引 chunks.jsonl 里含 18485 的块数 ====="
grep -c '18485' /data/fagui_rag/index/chunks.jsonl || echo 0
echo "===== 2) 含 18484 的块数 ====="
grep -c '18484' /data/fagui_rag/index/chunks.jsonl || echo 0
echo "===== 3) 命中块的标题（前 5 条）====="
grep -m5 '18485' /data/fagui_rag/index/chunks.jsonl | python3 - <<'PY'
import sys, json
for line in sys.stdin:
    try:
        d = json.loads(line)
    except Exception:
        continue
    print("  -", d.get("title"), "|", (d.get("text") or "")[:70].replace("\n", " "))
PY
echo "===== 4) 含『生活垃圾焚烧污染控制标准』字样的块数 ====="
grep -c '生活垃圾焚烧污染控制标准' /data/fagui_rag/index/chunks.jsonl || echo 0
echo "===== 5) 语料目录里文件名带 18485/18484 的 ====="
find /data/fagui_rag -iname '*18485*' 2>/dev/null | head -5
find /data/fagui_rag -iname '*18484*' 2>/dev/null | head -5
echo "===== 6) 语料里文件名含『焚烧污染控制』的 ====="
find /data/fagui_rag -iname '*焚烧污染控制*' 2>/dev/null | head -10
echo "===== 7) 工作区语料目录（若在）====="
ls -d /data/fagui_rag/* 2>/dev/null | head -20
