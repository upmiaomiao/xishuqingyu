#!/bin/bash
echo "=== 1. 索引目录结构 ==="
ls -la /data/fagui_rag/index/ | head -20

echo
echo "=== 2. retriever 怎么加载索引、source 字段从哪来 ==="
sed -n '1,60p' /data/fagui_rag/retriever.py

echo
echo "=== 3. okf_bundles 结构（source 前缀可能就是它）==="
ls /data/fagui_rag/okf_bundles | head -20
echo "--- 顶层目录数 ---"
ls /data/fagui_rag/okf_bundles | wc -l
echo "--- eia_reports_raw 里 .md 数 ---"
ls /data/fagui_rag/eia_reports_raw/*.md 2>/dev/null | wc -l
