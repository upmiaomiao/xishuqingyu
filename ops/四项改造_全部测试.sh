#!/bin/bash
# 本次「四项改造」相关的全部服务端测试，一次跑完。
#
# 为什么要有这个脚本：改完之后分散跑容易漏掉某一套，
# 而漏掉的那套往往正是会红的那套。集中跑一遍，最后给一个总账。
set -u

PY=/home/test/fagui_serve/.venv/bin/python
PASS=0
FAIL=0
FAILED_NAMES=""

run() {
  local label="$1"; shift
  echo
  echo "############################################################"
  echo "# $label"
  echo "############################################################"
  if "$@"; then
    echo "---- [通过] $label"
    PASS=$((PASS + 1))
  else
    echo "---- [失败] $label"
    FAIL=$((FAIL + 1))
    FAILED_NAMES="$FAILED_NAMES\n  · $label"
  fi
}

run "韧性层单测（重试/降级/缓存 31 条）" \
    "$PY" /home/test/查韧性层.py

run "原文回退实测（/doc/info + /doc/text）" \
    "$PY" /home/test/查原文回退_实测.py

run "缓存与步骤收尾实测（真实 SSE）" \
    "$PY" /home/test/查缓存与收尾_实测.py

echo
echo "############################################################"
echo "# 总账"
echo "############################################################"
echo "  通过 $PASS 套，失败 $FAIL 套"
if [ "$FAIL" != "0" ]; then
  echo -e "  失败的：$FAILED_NAMES"
  exit 1
fi
echo "  全部通过。"
