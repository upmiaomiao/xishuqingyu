#!/bin/sh
# 只读排查第二轮：精确量化「可回收空间」。
# 本脚本只统计，不删除任何东西。
set -u

echo "===== A. docker 存储后端确认 ====="
sudo -n cat /etc/docker/daemon.json 2>&1
echo "--- docker info 存储驱动 ---"
sudo -n docker info 2>&1 | grep -iE 'storage driver|docker root dir|backing|containerd' | head -10

echo
echo "===== B. docker system df 总览 ====="
sudo -n docker system df 2>&1

echo
echo "===== C. 悬空镜像 / 未使用镜像 ====="
echo "--- dangling (<none>) ---"
sudo -n docker images -f dangling=true --format '{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}' 2>&1
echo
echo "--- 全部镜像（含使用中的容器数）---"
sudo -n docker ps -a --format '{{.Image}}' 2>&1 | sort | uniq -c | sort -rn > /tmp/_used_images.txt
sudo -n docker images --format '{{.Repository}}:{{.Tag}}|{{.ID}}|{{.Size}}|{{.CreatedSince}}' 2>&1 | while IFS='|' read -r repo id size created; do
  n=$(grep -c -x -F "$repo" /tmp/_used_images.txt 2>/dev/null || echo 0)
  used=$(awk -v r="$repo" '$2==r {print $1}' /tmp/_used_images.txt)
  printf '%-58s %-14s %-10s %-16s containers=%s\n' "$repo" "$id" "$size" "$created" "${used:-0}"
done

echo
echo "===== D. buildx / 构建缓存 ====="
sudo -n docker buildx du 2>&1 | tail -15

echo
echo "===== E. 容器可写层占用 top ====="
sudo -n docker ps -a --size --format '{{.Names}}|{{.Size}}|{{.Status}}' 2>&1 | sort -t'|' -k2 -hr | head -20

echo
echo "===== F. containerd 各命名空间快照数 ====="
for ns in moby moby_history; do
  printf '%-14s images=%-5s containers=%-5s snapshots=%s\n' "$ns" \
    "$(sudo -n ctr -n $ns images ls -q 2>/dev/null | wc -l)" \
    "$(sudo -n ctr -n $ns containers ls -q 2>/dev/null | wc -l)" \
    "$(sudo -n ctr -n $ns snapshots ls 2>/dev/null | wc -l)"
done

echo
echo "===== G. containerd 快照磁盘占用 top 20 ====="
S=/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots
sudo -n du -sh $S/* 2>/dev/null | sort -hr | head -20

echo
echo "===== H. huggingface 缓存明细（top 25）====="
du -sh /home/test/.cache/huggingface/* 2>/dev/null | sort -hr | head -10
echo "--- hub 下每个模型 ---"
du -sh /home/test/.cache/huggingface/hub/* 2>/dev/null | sort -hr | head -25

echo
echo "===== I. vscode-server 版本占用 ====="
du -sh /home/test/.vscode-server/* 2>/dev/null | sort -hr | head -10
echo "--- cli/servers 明细 ---"
du -sh /home/test/.vscode-server/cli/servers/* 2>/dev/null | sort -hr | head -10
du -sh /home/test/.vscode-server/bin/* 2>/dev/null | sort -hr | head -10

echo
echo "===== J. agent_platform 旧备份 ====="
ls -d /home/test/agent_platform.bak* 2>/dev/null | while read d; do printf '%s  %s\n' "$(du -sh $d 2>/dev/null | cut -f1)" "$d"; done

echo
echo "===== K. 日志与包缓存 ====="
sudo -n journalctl --disk-usage 2>&1
du -sh /var/cache/apt /var/lib/apt/lists /var/log 2>/dev/null
echo "--- /var/log 下 top 10 ---"
sudo -n du -sh /var/log/* 2>/dev/null | sort -hr | head -10

echo
echo "===== L. /tmp 大项（>50M）====="
sudo -n du -sh /tmp/* 2>/dev/null | sort -hr | head -15 | grep -E '^[0-9.]+[MG]' 
echo "--- /tmp 空目录/小文件个数 ---"
sudo -n find /tmp -maxdepth 1 -mindepth 1 2>/dev/null | wc -l

echo
echo "===== M. /root/.cache ====="
sudo -n du -sh /root/.cache/* 2>/dev/null | sort -hr | head -10

echo
echo "===== N. /home/test 其他可清理候选 ====="
for d in /home/test/.cache/vllm /home/test/.cache/modelscope /home/test/.triton /home/test/.codegeex /home/test/.codex /home/test/.npm /home/test/.nvm /home/test/.local /home/test/.docker /home/test/.humming /home/test/.dotnet /home/test/.tilelang; do
  [ -e "$d" ] && printf '%-40s %s\n' "$d" "$(du -sh $d 2>/dev/null | cut -f1)"
done
echo "--- pip/uv 缓存是否已指向 /data ---"
ls -la /home/test/.cache/ 2>/dev/null | grep -E 'pip|uv'
echo "--- 旧日志/临时产物 ---"
ls -la /home/test/*.log /home/test/nohup.out /home/test/*.tar /home/test/*.tar.gz /home/test/*.zip 2>/dev/null | head -20

echo "===== done ====="
