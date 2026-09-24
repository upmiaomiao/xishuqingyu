#!/bin/bash
# 查服务器能不能承担"建仓库并推送"：git 版本、身份、出网、凭据助手。
echo "==== git ===="
git --version 2>&1
echo "user.name  = $(git config --global --get user.name 2>&1)"
echo "user.email = $(git config --global --get user.email 2>&1)"
echo "credential.helper = $(git config --global --get credential.helper 2>&1)"
echo "==== 出网（github / gitee，443）===="
for h in github.com gitee.com; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 12 "https://$h" 2>/dev/null)
  echo "  $h → HTTP ${code:-失败}"
done
echo "==== 已有 git 仓库？ ===="
for d in /home/test/xishu_qingyu_serve /data/eia_audit /data/eia_report_gen /home/test; do
  [ -d "$d/.git" ] && echo "  $d 是 git 仓库" || echo "  $d 不是 git 仓库"
done
echo "==== 磁盘余量（建仓库用）===="
df -h /home/test | tail -1
