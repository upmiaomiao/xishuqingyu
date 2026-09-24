#!/bin/bash
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
echo "=== 1. 全部生成任务清单 ==="
curl -s -m 20 http://127.0.0.1:8011/gen/api/jobs \
  | /home/test/fagui_serve/.venv/bin/python -c "
import json,sys
d=json.load(sys.stdin)
for j in d.get('jobs',[]):
    print('  %-14s %-8s %-22s %s' % (j.get('id'), j.get('status'), j.get('created'), (j.get('file') or '(无产物)')))
print('  共 %d 个任务' % len(d.get('jobs',[])))
"

echo
echo "=== 2. 日志中 /gen/api/run 前后的上下文（定位是哪个脚本）==="
for ln in 491 549 553 557; do
  echo "---- 第 $ln 行附近 ----"
  sed -n "$((ln-6)),$((ln+2))p" $LOG
done

echo
echo "=== 3. 日志里出现过的脚本特征路径（区分我的各个测试脚本）==="
grep -oE '"(GET|POST) [^ ]+' $LOG | sort | uniq -c | sort -rn | head -25
