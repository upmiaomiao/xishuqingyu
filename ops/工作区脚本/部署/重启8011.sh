#!/usr/bin/env bash
# 重启线上 8011（用原启动脚本，不改动它）并核验索引已加载
set -u
L=/home/test/xishu_qingyu_serve/launch_xishu_qingyu_qa_8011.sh

echo "==== launcher md5（应保持不变）===="
md5sum "$L"

echo
echo "==== 重启 ===="
bash "$L" stop
sleep 3
bash "$L" start
sleep 8

echo
echo "==== health ===="
curl -fsS http://127.0.0.1:8011/health; echo

echo
echo "==== 索引加载日志 ===="
grep -e Retriever -e chunks /home/test/xishu_qingyu_serve/qa_8011.log | tail -3

echo
echo "==== 进程 ===="
pgrep -af xishu_qingyu_qa | head -2
