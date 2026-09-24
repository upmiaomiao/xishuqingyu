#!/bin/bash
D=/home/test/xishu_qingyu_serve
cd $D || exit 1

echo "=== 1. 备份改动前的两个源文件 ==="
for f in xishu_pipeline/llm.py xishu_pipeline/pipeline.py; do
  cp -p "$f" "$f.bak_photojson_20260918"
  echo "  $(md5sum "$f" | cut -d' ' -f1)  $f"
  echo "  $(md5sum "$f.bak_photojson_20260918" | cut -d' ' -f1)  $f.bak_photojson_20260918"
done

echo
echo "=== 2. 目录里的启动/停止脚本（找出冻结的那个，我不碰）==="
ls -l $D/*.sh 2>/dev/null
echo "--- 各脚本 md5（fdabd26175e125d4d0ca62ac4abffce1 是冻结启动器）---"
md5sum $D/*.sh 2>/dev/null

echo
echo "=== 3. 当前站点进程是怎么起的 ==="
ps -o pid,ppid,lstart,cmd -p 2194863 2>/dev/null

echo
echo "=== 4. 站点相关端口 ==="
ss -tlnp 2>/dev/null | grep -E ':8011|:8020|:34004|:34005|:8012'
