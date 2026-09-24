#!/bin/sh
# 判断 weaviate 反复重启是不是本次清理造成的
set -u

echo "===== 1. weaviate 重启次数与启动时间 ====="
sudo -n docker inspect ruoyi-ai-weaviate \
  --format 'RestartCount={{.RestartCount}}  StartedAt={{.State.StartedAt}}  Status={{.State.Status}}  ExitCode={{.State.ExitCode}}' 2>&1

echo
echo "===== 2. weaviate 最近日志 ====="
sudo -n docker logs --tail 15 ruoyi-ai-weaviate 2>&1

echo
echo "===== 3. weaviate 所用镜像是否还在（不该被删）====="
sudo -n docker inspect ruoyi-ai-weaviate --format 'Image={{.Config.Image}}' 2>&1
sudo -n docker images semitechnologies/weaviate --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}' 2>&1

echo
echo "===== 4. 对照：其他长期容器 ====="
for c in ruoyi-ai-backend ruoyi-ai-mysql ruoyi-ai-redis ruoyi-ai-admin ruoyi-ai-web xishu-qingyu-v5-gpu12; do
  sudo -n docker inspect "$c" \
    --format '{{.RestartCount}}  {{.Name}}  StartedAt={{.State.StartedAt}}' 2>&1
done

echo
echo "===== 5. 所有容器的 RestartCount 排行 ====="
sudo -n docker ps -aq 2>/dev/null | while read -r c; do
  sudo -n docker inspect "$c" --format '{{.RestartCount}}|{{.Name}}|{{.State.StartedAt}}' 2>/dev/null
done | sort -rn | head -8

echo
echo "===== 6. weaviate 是否曾成功就绪过（日志里找 ready）====="
sudo -n docker logs ruoyi-ai-weaviate 2>&1 | grep -iE 'ready|started|listening|error' | tail -8

echo "===== done ====="
