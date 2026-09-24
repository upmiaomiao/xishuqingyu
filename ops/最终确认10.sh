#!/bin/sh
# 最终状态确认
set -u

echo "===== 1. 时间与磁盘 ====="
date; df -h /; df -i / | tail -1

echo
echo "===== 2. 该新镜像是否已被容器使用 ====="
sudo -n docker ps -a --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>&1 | grep -i llmdoc || echo "  仍无容器引用"

echo
echo "===== 3. 容器总数（对照：清理前 46 running / 52 all）====="
echo "running: $(sudo -n docker ps -q 2>/dev/null | wc -l)    all: $(sudo -n docker ps -aq 2>/dev/null | wc -l)"

echo
echo "===== 4. 关键服务健康（真实端点）====="
probe() { printf '  %-42s -> %s\n' "$1" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$2" 2>/dev/null)"; }
probe "8011 生产站点 /health"          "http://127.0.0.1:8011/health"
probe "8010 uvicorn /docs"             "http://127.0.0.1:8010/docs"
probe "8000 vLLM /v1/models"           "http://127.0.0.1:8000/v1/models"
probe "8002 vLLM /v1/models"           "http://127.0.0.1:8002/v1/models"
probe "33001 vLLM qwen-8b /v1/models"  "http://127.0.0.1:33001/v1/models"
probe "35004 bge-m3 /v1/models"        "http://127.0.0.1:35004/v1/models"
probe "35005 bge-rerank /v1/models"    "http://127.0.0.1:35005/v1/models"
probe "18000 monitoring-plan /docs"    "http://127.0.0.1:18000/docs"
probe "8080 agent-platform /"          "http://127.0.0.1:8080/"
probe "38081 aic_portal /"             "http://127.0.0.1:38081/"
probe "6006 tensorboard /"             "http://127.0.0.1:6006/"

echo
echo "===== 5. 8011 业务自检 ====="
curl -s --max-time 10 http://127.0.0.1:8011/health 2>&1 | head -3

echo
echo "===== 6. 镜像与空间总账 ====="
sudo -n docker system df 2>&1
echo "--- containerd ---"
sudo -n du -x -sh /var/lib/containerd 2>/dev/null

echo
echo "===== 7. 被删的 24 个镜像确认已不在 ====="
for r in hub-nj.iwhalecloud.com/dmcit2024/llmdoc-gpu-service:C_202603191800 \
         hiyouga/llamafactory:0.9.4 \
         load_forecast_api-load-forecast-api:latest \
         teableio/teable:release.2026-07-13T08-11-52Z.2208 \
         mysql:8.0 ubuntu:22.04 nginx:alpine \
         semitechnologies/weaviate:1.29.2 \
         nvidia/cuda:12.8.0-base-ubuntu22.04 \
         langgenius/dify-web:1.13.3 \
         dify-web:1.13.3-self20260716 \
         dify-web:1.13.3-self20260717-3 \
         bakey1985/agent-platform-backend:latest; do
  if sudo -n docker images -q "$r" 2>/dev/null | grep -q .; then echo "  仍存在: $r"; else echo "  已删除: $r"; fi
done

echo
echo "===== 8. 在跑的镜像都还在（抽样 12 个）====="
for r in vllm/vllm-openai:v0.19.1 vllm/vllm-openai:v0.14.1 mysql:8.4 langgenius/dify-api:1.13.3 \
         atlassian/confluence:10.2.3 minio/minio:RELEASE.2025-09-07T16-13-09Z \
         semitechnologies/weaviate:1.30.0 hub.zentao.net/app/zentao:22.3 \
         buildingsbench_api-load-forecast-api:latest opendsm_api_service-opendsm-api:latest \
         redis:6.2 ghcr.io/ageerle/ruoyi-ai-backend:v3.1.0; do
  if sudo -n docker images -q "$r" 2>/dev/null | grep -q .; then echo "  在: $r"; else echo "  [!] 丢失: $r"; fi
done

echo "===== done ====="
