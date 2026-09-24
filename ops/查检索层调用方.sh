#!/usr/bin/env bash
# 查谁在用 Retriever / retriever，以及用法（参数、是否用 search/rerank 等底层方法）
set -u
echo "===== 1) 站点里所有引用点 ====="
grep -rn "retriever\.\|Retriever(\|fagui_rag" /home/test/xishu_qingyu_serve --include="*.py" 2>/dev/null \
  | grep -v "\.bak" | grep -v "^Binary"

echo
echo "===== 2) gen_routes.py 里的用法上下文 ====="
grep -n -B3 -A6 "retriever\|Retriever" /home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py 2>/dev/null | head -60

echo
echo "===== 3) 有没有别的地方也 import /data/fagui_rag 下的模块 ====="
grep -rln "fagui_rag" /data --include="*.py" 2>/dev/null | grep -v "okf_bundles" | head -20

echo
echo "===== 4) 线上 retriever.py 当前指纹（部署前记录） ====="
md5sum /data/fagui_rag/retriever.py
ls -la /data/fagui_rag/retriever.py
