#!/bin/bash
echo "=== .10 全部 GPU 计算进程（按卡）==="
nvidia-smi --query-compute-apps=gpu_uuid,pid,used_memory,process_name --format=csv,noheader | head -20
echo
nvidia-smi --query-gpu=index,uuid --format=csv,noheader | sed 's/^/  /'
echo
echo "=== rerank 服务(34005) 日志里的 400 ==="
grep -iE "400|bad request|error" /home/test/xishu_qingyu_serve/vllm_bge_rerank_34005.log 2>/dev/null | tail -6 | cut -c1-220
echo "  —— 日志尾 ——"
tail -3 /home/test/xishu_qingyu_serve/vllm_bge_rerank_34005.log 2>/dev/null | cut -c1-200
echo
echo "=== embed 服务(34004) 日志尾 ==="
tail -3 /home/test/xishu_qingyu_serve/vllm_bge_m3_34004.log 2>/dev/null | cut -c1-200
echo
echo "=== 34005 直连试探（空/正常请求）==="
curl -s -m 8 -o /dev/null -w "  正常请求 → HTTP %{http_code}  %{time_total}s\n" \
  -X POST http://127.0.0.1:34005/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"bge-reranker-v2-m3","query":"垃圾焚烧炉渣","documents":["炉渣热灼减率"]}'
curl -s -m 8 -w "\n  空 documents → HTTP %{http_code}\n" \
  -X POST http://127.0.0.1:34005/v1/rerank -H 'Content-Type: application/json' \
  -d '{"model":"bge-reranker-v2-m3","query":"垃圾焚烧炉渣","documents":[]}' | cut -c1-300
echo
echo "=== 站点健康接口内容 ==="
curl -s -m 5 http://127.0.0.1:8011/health | head -c 400; echo
echo
echo "=== 谁在连站点（最近连接来源）==="
ss -tn state established '( sport = :8011 )' 2>/dev/null | awk 'NR>1{print "  "$4" ← "$5}' | head -8
echo
echo "=== .10 系统盘 / 剩余与日志占用 ==="
df -h / | tail -1 | sed 's/^/  /'
journalctl --disk-usage 2>/dev/null | sed 's/^/  /'
