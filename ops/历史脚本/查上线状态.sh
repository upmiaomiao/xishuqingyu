#!/bin/bash
# 站点上线状态全面盘点（在 10.201.31.10 本机执行）
# 用法：bash /home/test/查上线状态.sh

echo "=== 0. 主机 / 时间 ==="
hostname
date
uptime | head -1

echo
echo "=== 1. 关键端口监听 ==="
ss -ltnp 2>/dev/null | grep -E ':(8011|8012|8013|8020|34004|34005|8000|8003|8004|8100) ' | sed 's/  */ /g'

echo
echo "=== 2. 站点进程 ==="
ps -eo pid,etime,cmd | grep -E '[x]ishu_qingyu_serve|[l]aunch_xishu' | head -20

echo
echo "=== 3. 站点 HTTP 状态码 ==="
for p in /health /kg/stats / /gen /audit /docs /openapi.json; do
  printf "%-16s -> %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:8011$p)"
done

echo
echo "--- health 正文 ---"
curl -s -m 10 http://127.0.0.1:8011/health
echo
echo "--- kg/stats 正文 ---"
curl -s -m 10 http://127.0.0.1:8011/kg/stats
echo
echo "--- gen/api/outputs 条数 ---"
curl -s -m 10 http://127.0.0.1:8011/gen/api/outputs | head -c 400

echo
echo "=== 4. 三个依赖服务 ==="
echo "--- 8020 v5 ---"
curl -s -m 10 http://127.0.0.1:8020/v1/models | head -c 400
echo
echo "--- 34004 embedding ---"
curl -s -m 10 http://127.0.0.1:34004/v1/models | head -c 400
echo
echo "--- 34005 rerank 存活 ---"
curl -s -o /dev/null -w 'HTTP %{http_code}\n' -m 10 http://127.0.0.1:34005/v1/rerank

echo
echo "=== 5. config.py 关键行 ==="
grep -nE 'MODEL_URL|KG_PATH|MODEL_NAME|^BASE_DIR' /home/test/xishu_qingyu_serve/xishu_pipeline/config.py

echo
echo "=== 6. 冻结脚本 md5（应为 fdabd26175e125d4d0ca62ac4abffce1）==="
md5sum /home/test/xishu_qingyu_serve/launch_xishu_qingyu_qa_8011.sh

echo
echo "=== 7. GPU ==="
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader

echo
echo "=== 8. 磁盘 ==="
df -h / /data /home 2>/dev/null | sed 's/  */ /g'

echo
echo "=== 9. 日志里的 rerank 降级 / 检索异常 ==="
for f in $(ls -t /home/test/xishu_qingyu_serve/*.log 2>/dev/null | head -3); do
  echo "[$f]"
  echo "  rerank failed  : $(grep -c 'rerank failed' $f 2>/dev/null)"
  echo "  检索服务异常   : $(grep -c '检索服务异常' $f 2>/dev/null)"
  echo "  最后修改       : $(stat -c '%y' $f 2>/dev/null)"
done

echo
echo "=== 10. 图谱文件 ==="
ls -l /home/test/xishu_qingyu_serve/kg_data/graph_full.json 2>/dev/null

echo
echo "=== 11. v5 权重（.10 本地）==="
ls -l /data/sft/env_sft/xishu_qingyu_v5_final/model.safetensors.index.json 2>/dev/null
du -sh /data/sft/env_sft/xishu_qingyu_v5_final 2>/dev/null

echo
echo "=== 12. .12 上的 v5 是否还在跑（冗余备份）==="
ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 10.201.31.12 "ss -ltn 2>/dev/null | grep ':8000 ' ; nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | head -4" 2>&1 | head -10
