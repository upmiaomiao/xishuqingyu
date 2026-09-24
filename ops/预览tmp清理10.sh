#!/bin/sh
# 只读预览：tier1 的 /tmp 白名单到底会删哪些、省多少、哪些会保留。
set -u

{
  find /tmp -maxdepth 1 -mindepth 1 -mtime +3 2>/dev/null | grep -E \
    '^/tmp/(pymp-|wandb-|torchelastic_|mcp-|pyright-|code-|vscode-|dify_diag_|tmp.*-wandb-|tmp[0-9a-zA-Z_]{6,}$|tmp_[0-9a-zA-Z_]{5,}$)'
  printf '%s\n' \
    /tmp/torchinductor_root /tmp/torchinductor_test /tmp/piptest \
    /tmp/node-compile-cache /tmp/data-gym-cache /tmp/tvm-debug-mode-tempdirs \
    /tmp/stage_probe /tmp/rag_smoke /tmp/frontend_dist /tmp/agent_platform_new \
    /tmp/agent_platform_prod_backup /tmp/ray_tmp_math /tmp/ray_tmp_grpo \
    /tmp/ab_orch.log /tmp/debug-cli.test.log /tmp/serve_8000.log
  find /tmp -maxdepth 1 -mindepth 1 \( -name 'ap_tar_*' -o -name 'deploy_*' -o -name 'pytest-of-*' \) 2>/dev/null
} | sort -u > /tmp/_wl.txt

echo "=== 命中条目数 ==="
wc -l < /tmp/_wl.txt

echo
echo "=== 会被删的（按大小 top 20）==="
while read -r p; do
  [ -e "$p" ] && du -sh "$p" 2>/dev/null
done < /tmp/_wl.txt | sort -hr | head -20

echo
echo "=== 合计可释放 ==="
while read -r p; do
  [ -e "$p" ] && du -sk "$p" 2>/dev/null
done < /tmp/_wl.txt | awk '{s+=$1} END {printf "%.2f GB\n", s/1048576}'

echo
echo "=== 未被选中、将保留的 /tmp 顶层项（前 40）==="
find /tmp -maxdepth 1 -mindepth 1 2>/dev/null | grep -vxF -f /tmp/_wl.txt | head -40

echo
echo "=== 保留项里体积 >10M 的 ==="
find /tmp -maxdepth 1 -mindepth 1 2>/dev/null | grep -vxF -f /tmp/_wl.txt | while read -r p; do
  du -sh "$p" 2>/dev/null
done | sort -hr | head -15
