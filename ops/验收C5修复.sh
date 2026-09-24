#!/bin/bash
# 服务器侧验收：C5 专项单测 + 审核引擎自检（用带 fitz 的解释器）。
set -u
echo "==== 0) 找带 fitz 的解释器 ===="
for p in /data/eia_audit/.venv/bin/python /home/test/fagui_serve/.venv/bin/python \
         /data/fagui_rag/.venv_tools/bin/python /home/test/xishu_qingyu_serve/.venv/bin/python; do
  if [ -x "$p" ]; then
    v=$("$p" -c 'import fitz,sys;print(sys.version.split()[0])' 2>/dev/null)
    echo "  $p  fitz=$([ -n "$v" ] && echo 有 $v || echo 无)"
  fi
done
VENV=$(for p in /data/eia_audit/.venv/bin/python /home/test/fagui_serve/.venv/bin/python \
              /data/fagui_rag/.venv_tools/bin/python; do
         "$p" -c 'import fitz' 2>/dev/null && { echo "$p"; break; }
       done)
echo "  选用：${VENV:-未找到}"

echo
echo "==== 1) C5 专项单测 ===="
EIA_ENGINE_DIR=/data/eia_audit EIA_CRITERIA_DIR=/data/fagui_rag/criteria \
  python3 /home/test/单测_C5名录匹配.py 2>&1 | tail -22

echo
echo "==== 2) 审核引擎自检 selfcheck.py ===="
if [ -n "$VENV" ]; then
  cd /data/eia_audit && EIA_CRITERIA_DIR=/data/fagui_rag/criteria "$VENV" selfcheck.py 2>&1 | tail -8
else
  echo "  跳过（没有带 fitz 的解释器）"
fi

echo
echo "==== 3) 线上判据库文件时间戳（确认未被动过）===="
ls -l --time-style=+%Y-%m-%d\ %H:%M /data/fagui_rag/criteria/ | head -8
