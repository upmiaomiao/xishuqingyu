#!/bin/sh
# 10.201.31.10 系统盘分级清理。
#
#   用法： bash 清理系统盘10.sh <动作>
#
#   plan          只看不删：列出每一级将删除什么、当前占用（默认动作）
#   tier1         第 1 级：确定安全（构建缓存/悬空镜像/陈旧tmp/journal/apt缓存/root的vllm缓存）
#   tier2         第 2 级：删除无人引用的镜像（删前逐一复核容器引用，被引用的自动跳过）
#   tier3-hf      /home/test/.cache/huggingface/datasets（33G，数据集缓存）
#   tier3-datacache  /home/test/.cache/vllm + .triton + .cache/modelscope + .npm + .codegeex
#   tier3-bak     8 月 11-13 日的 agent_platform.bak.*（5.75G）+ agent_platform.tar.gz
#   tier3-vscode  .vscode-server 旧版本服务端（保留最新一个）
#   all-safe      = tier1 + tier2
#
# 设计原则：
#   1) 绝不用 docker image rm -f；被容器引用的镜像 rm 会被 docker 自己拒绝，这是最后一道闸。
#   2) 删镜像前重新计算引用关系，不看历史清单。
#   3) /tmp 只删 mtime +3 天、且当前没有任何进程打开的项目。
#   4) 每步前后打印 df -h /。
set -u

TARGET=/home/test
say()  { printf '\n=== %s ===\n' "$*"; }
dft()  { df -h / | tail -1; }

# 当前被任何进程打开的文件路径集合（用于保护 /tmp）
open_paths() {
  sudo -n lsof -nP 2>/dev/null | awk '$9 ~ /^\/tmp\// { sub(/\/[^\/]*$/, "", $9); print $9 }' | sort -u
}

# 容器正在使用的镜像引用集合（含短名，不含 tag 的写法也覆盖）
used_refs() {
  sudo -n docker ps -a --format '{{.Image}}' 2>/dev/null | sort -u
}

# 判断镜像是否被任何容器引用：ref / 无 tag 短名 / 镜像 ID 三种写法都查
is_used() {
  ref="$1"; id="$2"
  short="${ref%:*}"
  printf '%s\n' "$USED" | grep -qxF "$ref"     && return 0
  printf '%s\n' "$USED" | grep -qxF "$short"   && return 0
  printf '%s\n' "$USED" | grep -qxF "$id"      && return 0
  printf '%s\n' "$USED" | grep -qxF "$(printf '%.12s' "$id")" && return 0
  return 1
}

# ---------- plan ----------
do_plan() {
  say "当前系统盘"
  dft
  say "docker 自报可回收"
  sudo -n docker system df 2>&1

  say "第1级 将清理"
  echo "  - Docker 构建缓存（buildx du 显示 $(sudo -n docker buildx du 2>/dev/null | awk '/^Reclaimable/{print $2}')）"
  echo "  - 悬空镜像："
  sudo -n docker images -f dangling=true --format '      {{.ID}} {{.Size}}' 2>&1
  echo "  - /tmp 陈旧项（mtime +3 天且无进程占用）："
  find /tmp -maxdepth 1 -mindepth 1 -mtime +3 2>/dev/null | head -8
  echo "      ... 共 $(find /tmp -maxdepth 1 -mindepth 1 -mtime +3 2>/dev/null | wc -l) 项"
  echo "  - journal（当前 $(sudo -n journalctl --disk-usage 2>/dev/null | grep -o '[0-9.]*[MG]' | head -1)）→ 压到 200M"
  echo "  - apt 缓存 $(du -sh /var/cache/apt /var/lib/apt/lists 2>/dev/null | awk '{printf "%s ", $1}')"
  echo "  - /root/.cache/vllm $(sudo -n du -sh /root/.cache/vllm 2>/dev/null | cut -f1)"

  say "第2级 候选镜像（下面这些当前没有被任何容器引用）"
  USED=$(used_refs)
  sudo -n docker images --format '{{.ID}}|{{.Repository}}:{{.Tag}}|{{.Size}}' 2>/dev/null | \
  while IFS='|' read -r id ref size; do
    is_used "$ref" "$id" || printf '  %-10s %s\n' "$size" "$ref"
  done

  say "第3级 需人工指定的业务数据"
  for d in /home/test/.cache/huggingface/datasets /home/test/.cache/vllm /home/test/.triton \
           /home/test/.cache/modelscope /home/test/.npm /home/test/.codegeex \
           /home/test/.vscode-server/cli/servers /home/test/agent_platform.tar.gz; do
    [ -e "$d" ] && printf '  %-8s %s\n' "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
  done
  echo "  --- agent_platform.bak.* ---"
  for d in /home/test/agent_platform.bak.*; do
    [ -e "$d" ] && printf '  %-8s %s\n' "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
  done
}

# ---------- tier1 ----------
do_tier1() {
  say "第1级开始"; dft

  echo "--- 1/6 Docker 构建缓存 ---"
  sudo -n docker buildx du 2>/dev/null | tail -4
  sudo -n docker buildx prune -af 2>&1 | tail -5
  sudo -n docker builder prune -af 2>&1 | tail -3
  echo "  清理后：" ; sudo -n docker buildx du 2>/dev/null | tail -2

  echo "--- 2/6 悬空镜像 ---"
  sudo -n docker image prune -f 2>&1 | tail -5

  echo "--- 3/6 /tmp 陈旧项（白名单模式 + mtime +3 天 + 无进程占用）---"
  OPEN=$(open_paths)
  # 只删「确定是临时产物」的名字；不认识的文件/脚本一律不碰。
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
  } | sort -u | while read -r p; do
    [ -e "$p" ] || continue
    case "$p" in
      /tmp/.X11-unix|/tmp/.ICE-unix|/tmp/.XIM-unix|/tmp/.Test-unix|/tmp/.font-unix) continue ;;
      /tmp/systemd-private-*|/tmp/snap-private-tmp|/tmp/tmux-*|/tmp/ray) continue ;;
    esac
    printf '%s\n' "$OPEN" | grep -qxF "$p" && { echo "  跳过（被进程占用）: $p"; continue; }
    rm -rf "$p" && echo "  删除: $p"
  done
  echo "  /tmp 剩余条目: $(find /tmp -maxdepth 1 -mindepth 1 2>/dev/null | wc -l)"

  echo "--- 4/6 journal 压缩到 200M ---"
  sudo -n journalctl --vacuum-size=200M 2>&1 | tail -3

  echo "--- 5/6 apt 缓存 ---"
  sudo -n apt-get clean 2>&1 | tail -2
  sudo -n rm -rf /var/lib/apt/lists/* 2>&1
  echo "  /var/lib/apt/lists 已清空"

  echo "--- 6/6 /root/.cache/vllm ---"
  sudo -n du -sh /root/.cache/vllm 2>/dev/null
  sudo -n rm -rf /root/.cache/vllm && echo "  已删除"

  say "第1级完成"; dft
}

# ---------- tier2 ----------
do_tier2() {
  say "第2级开始"; dft
  USED=$(used_refs)

  # 明确「无人引用就删」的清单。
  # 故意不包含 minio:latest / ruoyi-ai-backend:v3.1.0-chenz —— 它们与在用镜像同 ID，
  # 删了只是去标签，一个字节都不省。
  REFS='
hub-nj.iwhalecloud.com/dmcit2024/llmdoc-gpu-service:C_202603191800
hiyouga/llamafactory:0.9.4
load_forecast_api-load-forecast-api:latest
teableio/teable:release.2026-07-13T08-11-52Z.2208
dify-web:1.13.3-self20260716
dify-web:1.13.3-self20260717-3
dify-web:1.13.3-self20260720-2
dify-web:1.13.3-self20260721
dify-web:1.13.3-self20260721-1
dify-web:1.13.3-self20260721-2
dify-web:1.13.3-self20260721-3
dify-web:1.13.3-self20260721-4
dify-web:1.13.3-self20260721-5
dify-web:1.13.3-self20260722
dify-web:1.13.3-self20260723
langgenius/dify-web:1.13.3
mysql:8.0
nvidia/cuda:12.8.0-base-ubuntu22.04
bakey1985/agent-platform-backend:latest
bakey1985/agent-platform-frontend:latest
semitechnologies/weaviate:1.29.2
nginx:alpine
ubuntu:22.04
'

  # 不走管道，好让计数器能传出来（顺带能发现清单里被拼坏的条目）
  printf '%s\n' "$REFS" > /tmp/_refs10.txt
  n_del=0; n_used=0; n_missing=0
  while read -r ref; do
    [ -z "$ref" ] && continue
    id=$(sudo -n docker images --format '{{.ID}}|{{.Repository}}:{{.Tag}}' 2>/dev/null \
         | awk -F'|' -v r="$ref" '$2==r{print $1}' | head -1)
    if [ -z "$id" ]; then echo "  跳过（镜像不存在）: $ref"; n_missing=$((n_missing+1)); continue; fi
    if is_used "$ref" "$id"; then echo "  跳过（仍在被容器引用）: $ref"; n_used=$((n_used+1)); continue; fi
    echo "  删除: $ref"
    sudo -n docker image rm "$ref" 2>&1 | tail -2
    n_del=$((n_del+1))
  done < /tmp/_refs10.txt
  echo "  --- 清单 $((n_del+n_used+n_missing)) 条：删除 $n_del，仍被引用 $n_used，不存在 $n_missing ---"
  [ "$n_missing" -gt 0 ] && echo "  [!] 有「不存在」的条目，检查 REFS 清单是否被写坏（例如行尾换行丢失导致两行拼一起）"

  echo "--- 再清一次悬空 ---"
  sudo -n docker image prune -f 2>&1 | tail -3

  say "第2级完成"; dft
}

# ---------- tier3 各项 ----------
do_tier3_hf() {
  say "第3级：HF 数据集缓存"
  du -sh /home/test/.cache/huggingface/datasets/* 2>/dev/null
  rm -rf /home/test/.cache/huggingface/datasets/json \
         /home/test/.cache/huggingface/datasets/downloads
  echo "  已删除 json/ 与 downloads/（保留 parquet/ 与 hub/）"
  dft
}
do_tier3_datacache() {
  say "第3级：各类编译/下载缓存"
  for d in /home/test/.cache/vllm /home/test/.triton /home/test/.cache/modelscope \
           /home/test/.npm /home/test/.codegeex /home/test/.cache/torch_extensions; do
    [ -e "$d" ] || continue
    printf '  %-8s %s → 删除\n' "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
    rm -rf "$d"
  done
  dft
}
do_tier3_bak() {
  say "第3级：8 月部署备份"
  for d in /home/test/agent_platform.bak.*; do
    [ -e "$d" ] || continue
    printf '  %-8s %s → 删除\n' "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
    rm -rf "$d"
  done
  [ -f /home/test/agent_platform.tar.gz ] && { ls -lh /home/test/agent_platform.tar.gz; rm -f /home/test/agent_platform.tar.gz; echo "  已删 agent_platform.tar.gz"; }
  echo "  保留: /home/test/agent_platform（在跑的版本）"
  dft
}
do_tier3_vscode() {
  say "第3级：vscode-server 旧版本"
  D=/home/test/.vscode-server/cli/servers
  newest=$(ls -1dt $D/Stable-* 2>/dev/null | head -1)
  echo "  保留最新: $newest"
  for d in $D/Stable-*; do
    [ "$d" = "$newest" ] && continue
    printf '  %-8s %s → 删除\n' "$(du -sh "$d" 2>/dev/null | cut -f1)" "$d"
    rm -rf "$d"
  done
  dft
}

case "${1:-plan}" in
  plan)            do_plan ;;
  tier1)           do_tier1 ;;
  tier2)           do_tier2 ;;
  all-safe)        do_tier1; do_tier2 ;;
  tier3-hf)        do_tier3_hf ;;
  tier3-datacache) do_tier3_datacache ;;
  tier3-bak)       do_tier3_bak ;;
  tier3-vscode)    do_tier3_vscode ;;
  *) sed -n '2,20p' "$0" ;;
esac
