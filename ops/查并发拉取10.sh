#!/bin/sh
# 判断 llmdoc-ocr-vl-gpu 是不是「正在被拉取」（有并发用户），并复核磁盘趋势
set -u

echo "===== 1. 现在时间与磁盘（与上次对比看趋势）====="
date
df -h /
echo "inode: $(df -i / | tail -1)"

echo
echo "===== 2. containerd 是否有未完成的 ingest（拉取中）====="
sudo -n ls -la /var/lib/containerd/io.containerd.content.v1.content/ingest/ 2>&1 | head -20
echo "  ingest 条目数: $(sudo -n ls -1 /var/lib/containerd/io.containerd.content.v1.content/ingest/ 2>/dev/null | wc -l)"

echo
echo "===== 3. blob 存储最近 60 分钟内被写入的文件 ====="
sudo -n find /var/lib/containerd/io.containerd.content.v1.content/blobs -type f -mmin -60 2>/dev/null | wc -l
echo "  最新 5 个:"
sudo -n find /var/lib/containerd/io.containerd.content.v1.content/blobs -type f -mmin -60 -printf '%TY-%Tm-%Td %TH:%TM  %s  %p\n' 2>/dev/null | sort -r | head -5

echo
echo "===== 4. snapshot 最近 60 分钟内被写入的 ====="
sudo -n find /var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/snapshots -maxdepth 1 -mmin -60 2>/dev/null | wc -l

echo
echo "===== 5. 是否有指向 registry 的活动连接（dockerd/containerd）====="
sudo -n ss -tnp 2>/dev/null | grep -E 'dockerd|containerd' | head -10
echo "  （空 = 当前没有在下载镜像）"

echo
echo "===== 6. 该镜像的层是否已全部下载完 ====="
sudo -n docker inspect llmdoc-ocr-vl-gpu:C_202608311500 \
  --format '{{range .RootFS.Layers}}{{.}}{{"\n"}}{{end}}' 2>&1 | head -30
echo "  层数: $(sudo -n docker inspect llmdoc-ocr-vl-gpu:C_202608311500 --format '{{len .RootFS.Layers}}' 2>/dev/null)"

echo
echo "===== 7. containerd 里这个镜像的内容状态 ====="
sudo -n ctr -n moby images ls 2>/dev/null | grep -i -E 'NAME|llmdoc'
echo "--- content 里该镜像的 blob 是否齐 ---"
sudo -n ctr -n moby content ls 2>/dev/null | wc -l

echo
echo "===== 8. 谁在操作（近期登录 + 历史命令线索）====="
who 2>&1 | tail -6
echo "--- last 最近 5 条 ---"
last -n 5 2>&1 | head -8

echo
echo "===== 9. 该镜像仓库名暗示的用途 ====="
sudo -n docker image inspect llmdoc-ocr-vl-gpu:C_202608311500 \
  --format 'RepoDigests={{.RepoDigests}}
Comment={{.Comment}}
Arch={{.Architecture}}
Labels={{.Config.Labels}}' 2>&1 | head -10

echo "===== done ====="
