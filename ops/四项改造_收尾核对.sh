#!/bin/bash
# 收尾核对：线上文件指纹 + 备份完整性。
#
# 为什么要单独核对本地与线上：约定是"工作副本和线上两边都要改"，
# 曾经只推了 js/*.js 没推 index.html，导致本地和线上不一致、白排查半天。
# 这里把线上的 md5 打出来，和本地工作副本对比。
set -u
S=/home/test/xishu_qingyu_serve

echo "=== 线上文件（本次改动过的 8 个）==="
for f in \
  xishu_pipeline/resilience.py \
  xishu_pipeline/pipeline.py \
  xishu_pipeline/routes.py \
  xishu_pipeline/config.py \
  frontend/index.html \
  frontend/app.css \
  frontend/js/ask.js \
  frontend/js/message.js \
  ; do
  if [ -f "$S/$f" ]; then
    printf '  %-32s %8d B  %s\n' "$f" "$(stat -c%s "$S/$f")" "$(md5sum "$S/$f" | cut -d' ' -f1)"
  else
    printf '  %-32s ★ 缺失\n' "$f"
  fi
done

echo
echo "=== 本次新增/修改的关键代码标记 ==="
printf '  %-46s %s\n' "routes.py 有 /doc/info"      "$(grep -c '"/doc/info"' $S/xishu_pipeline/routes.py)"
printf '  %-46s %s\n' "routes.py 有 /doc/text"      "$(grep -c '"/doc/text"' $S/xishu_pipeline/routes.py)"
printf '  %-46s %s\n' "routes.py 有 /cache/stats"   "$(grep -c '"/cache/stats"' $S/xishu_pipeline/routes.py)"
printf '  %-46s %s\n' "pipeline.py 用 stream_with_retry" "$(grep -c 'stream_with_retry' $S/xishu_pipeline/pipeline.py)"
printf '  %-46s %s\n' "pipeline.py 有资料直出降级"  "$(grep -c 'sources_digest' $S/xishu_pipeline/pipeline.py)"
printf '  %-46s %s\n' "pipeline.py 有 FAQ_CACHE"    "$(grep -c 'FAQ_CACHE' $S/xishu_pipeline/pipeline.py)"
printf '  %-46s %s\n' "ask.js 有 friendlyError"      "$(grep -c 'function friendlyError' $S/frontend/js/ask.js)"
printf '  %-46s %s\n' "message.js 有 streaming 折叠" "$(grep -c 'm.streaming === true' $S/frontend/js/message.js)"
printf '  %-46s %s\n' "message.js 先探测再加载"     "$(grep -c '/doc/info?source=' $S/frontend/js/message.js)"
printf '  %-46s %s\n' "index.html 有 docText"       "$(grep -c 'id="docText"' $S/frontend/index.html)"

echo
echo "=== 备份目录（回滚用）==="
D=/home/test/_重构归档_20260918/四项改造_前
ls -la "$D" | tail -9
echo "  文件数：$(ls "$D" | wc -l)（应为 7）"

echo
echo "=== 服务状态 ==="
PID=$(pgrep -f 'uvicorn' | head -1)
echo "  uvicorn pid = ${PID:-未找到}"
curl -s -o /dev/null -w '  GET /      -> %{http_code}\n' http://127.0.0.1:8011/
printf '  /health    -> %s\n' "$(curl -s --max-time 5 http://127.0.0.1:8011/health)"
printf '  /cache/stats -> %s\n' "$(curl -s --max-time 5 http://127.0.0.1:8011/cache/stats)"
