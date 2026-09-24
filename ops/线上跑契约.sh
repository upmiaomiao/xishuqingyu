#!/bin/bash
# 跑既有验收契约（A 档四件上线后，确认没有把别的东西碰坏）。只读、不改数据。
cd /home/test || exit 1
for f in 查界面契约.py 查嵌入契约.py 查生成界面契约.py 查补充信息契约.py 自测生成页.py; do
  if [ -f "$f" ]; then
    echo "================ $f"
    python3 "$f" 2>&1 | tail -4
  else
    echo "================ $f（服务器上没有，跳过）"
  fi
done
