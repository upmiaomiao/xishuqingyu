#!/bin/bash
# 安全重启 8011：**重启前先转存访问日志**
#
# 为什么需要它：launch_xishu_qingyu_qa_8011.sh 第 18 行是
#     nohup "$PYTHON" "$APP" >"$LOG_FILE" 2>&1 &
# 用的是 `>`（截断）而不是 `>>`，所以**每次重启都会把整个访问日志清空**。
# 2026-09-18 我就是因为这一点，查不到 09:48 那份草稿的请求记录（证据被自己的重启抹掉了）。
# 启动器是冻结的（md5 fdabd26175e125d4d0ca62ac4abffce1），不能改，所以在外面补一层保全。
set -e
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918/日志
mkdir -p "$ARC"

TS=$(date -u +%Y%m%d-%H%M%S)
if [ -s "$D/qa_8011.log" ]; then
  cp -p "$D/qa_8011.log" "$ARC/qa_8011_$TS.log"
  echo "[保全] 日志已转存 -> $ARC/qa_8011_$TS.log（$(wc -l < "$ARC/qa_8011_$TS.log") 行）"
else
  echo "[保全] 日志为空，跳过"
fi

echo "[重启] stop"
bash "$D/launch_xishu_qingyu_qa_8011.sh" stop >/dev/null 2>&1 || true
OLD=$(cat "$D/qa_8011.pid" 2>/dev/null || true)
for i in $(seq 1 20); do kill -0 "$OLD" 2>/dev/null || { echo "[重启] 第 ${i}s 已退出"; break; }; sleep 1; done
if kill -0 "$OLD" 2>/dev/null; then kill -9 "$OLD"; echo "[重启] 补 SIGKILL"; sleep 2; fi

bash "$D/launch_xishu_qingyu_qa_8011.sh" start
for i in $(seq 1 90); do
  curl -fsS -m 3 http://127.0.0.1:8011/health >/dev/null 2>&1 && { echo "[重启] 第 ${i}s /health 通"; break; }
  sleep 1
done
echo "[重启] pid $(cat "$D/qa_8011.pid")"
