#!/usr/bin/env bash
set -euo pipefail

APP=/home/test/xishu_qingyu_serve/xishu_qingyu_qa.py
PYTHON=/home/test/fagui_serve/.venv/bin/python
PID_FILE=/home/test/xishu_qingyu_serve/qa_8011.pid
LOG_FILE=/home/test/xishu_qingyu_serve/qa_8011.log

case "${1:-start}" in
  start)
    mkdir -p /home/test/xishu_qingyu_serve
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "already_running pid=$(cat "$PID_FILE")"
      exit 0
    fi
    export QA_HOST=0.0.0.0
    export QA_PORT=8011
    nohup "$PYTHON" "$APP" >"$LOG_FILE" 2>&1 &
    echo $! >"$PID_FILE"
    echo "started pid=$(cat "$PID_FILE") port=8011"
    ;;
  stop)
    [[ -f "$PID_FILE" ]] && kill "$(cat "$PID_FILE")" 2>/dev/null || true
    echo stopped
    ;;
  status)
    curl -fsS http://127.0.0.1:8011/health || true
    ;;
  logs) tail -f "$LOG_FILE" ;;
  *) echo "usage: $0 {start|stop|status|logs}" >&2; exit 2 ;;
esac
