#!/bin/sh
# 收尾：补删因脚本拼行 bug 漏掉的 2 个镜像 + 用真实端点复核服务健康。
set -u

echo "===== A. 补删漏掉的镜像 ====="
USED=$(sudo -n docker ps -a --format '{{.Image}}' 2>/dev/null | sort -u)
for ref in dify-web:1.13.3-self20260716 dify-web:1.13.3-self20260717-3; do
  id=$(sudo -n docker images --format '{{.ID}}|{{.Repository}}:{{.Tag}}' 2>/dev/null \
       | awk -F'|' -v r="$ref" '$2==r{print $1}' | head -1)
  if [ -z "$id" ]; then echo "  不存在: $ref"; continue; fi
  if printf '%s\n' "$USED" | grep -qxF "$ref"; then echo "  仍被引用，跳过: $ref"; continue; fi
  echo "  删除: $ref"
  sudo -n docker image rm "$ref" 2>&1 | tail -2
done

echo
echo "===== B. 服务真实端点复核（不是探 /）====="
probe() { printf '  %-46s -> %s\n' "$1" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 "$2" 2>/dev/null)"; }
probe "8011 生产站点 /health"        "http://127.0.0.1:8011/health"
probe "8011 生产站点 /"              "http://127.0.0.1:8011/"
probe "8010 uvicorn /docs"           "http://127.0.0.1:8010/docs"
probe "8000 vLLM qwen3.6 /v1/models" "http://127.0.0.1:8000/v1/models"
probe "8002 vLLM xiyan14b /v1/models" "http://127.0.0.1:8002/v1/models"
probe "33001 vLLM qwen-8b /v1/models" "http://127.0.0.1:33001/v1/models"
probe "35004 bge-m3 /v1/models"      "http://127.0.0.1:35004/v1/models"
probe "35005 bge-rerank /v1/models"  "http://127.0.0.1:35005/v1/models"
probe "18000 monitoring-plan /docs"  "http://127.0.0.1:18000/docs"
probe "38081 aic_portal /"           "http://127.0.0.1:38081/"
probe "8080 agent-platform /"        "http://127.0.0.1:8080/"
probe "28080 weaviate /v1/.well-known/ready" "http://127.0.0.1:28080/v1/.well-known/ready"
probe "6006 tensorboard /"           "http://127.0.0.1:6006/"

echo
echo "===== C. 生产站点 8011 业务自检 ====="
curl -s --max-time 10 http://127.0.0.1:8011/health 2>&1 | head -3

echo
echo "===== D. 最终空间 ====="
df -h /
echo "--- docker ---"
sudo -n docker system df 2>&1
echo "--- containerd ---"
sudo -n du -x -sh /var/lib/containerd 2>/dev/null

echo
echo "===== E. 容器存活对比（应仍为 running 46 / all 52）====="
echo "running: $(sudo -n docker ps -q 2>/dev/null | wc -l)    all: $(sudo -n docker ps -aq 2>/dev/null | wc -l)"

echo "===== done ====="
