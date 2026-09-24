#!/bin/bash
# 部署「四项改造」第 2 步：语法检查 → 重启 → 验活。
#
# ⚠ 启动器路径守卫是必须的：之前部署脚本写错了启动器路径，
#   pkill 已经把服务杀掉了，重启又用错路径 → 站点直接挂。
#   这个脚本在**动任何东西之前**先确认启动器和重启脚本都在。
set -u

SITE=/home/test/xishu_qingyu_serve
PY=/home/test/fagui_serve/.venv/bin/python
RESTART=/home/test/安全重启8011.sh
LAUNCHER=$SITE/launch_xishu_qingyu_qa_8011.sh

echo "=== 0. 守卫：启动器与重启脚本必须都在 ==="
miss=0
for f in "$RESTART" "$LAUNCHER"; do
  if [ -f "$f" ]; then echo "  √ $f"; else echo "  × 缺失：$f"; miss=1; fi
done
if [ "$miss" != "0" ]; then
  echo
  echo "启动器缺失，**不做任何改动**直接退出（防止把站点搞挂）。"
  exit 1
fi

echo
echo "=== 1. 新文件都在位吗 ==="
for f in \
  xishu_pipeline/config.py xishu_pipeline/routes.py \
  xishu_pipeline/pipeline.py xishu_pipeline/resilience.py \
  frontend/index.html frontend/app.css \
  frontend/js/ask.js frontend/js/message.js \
  ; do
  if [ -f "$SITE/$f" ]; then
    printf '  √ %-32s %6d B  %s\n' "$f" "$(stat -c%s "$SITE/$f")" "$(md5sum "$SITE/$f" | cut -c1-12)"
  else
    echo "  × 缺失：$f"; miss=1
  fi
done
[ "$miss" = "0" ] || { echo "有文件缺失，中止。"; exit 1; }

echo
echo "=== 2. 语法检查（py_compile）==="
# 注意：py_compile 只证明"能编译"，不证明"能 import"。
# 之前有过 py_compile 全绿但 import 就炸的事故（漏了一个导入的符号），
# 所以下面第 3 步必须真的把模块 import 一遍。
cd "$SITE"
if $PY -m py_compile xishu_pipeline/*.py; then
  echo "  全部编译通过"
else
  echo "  编译失败，中止（不重启，线上还是旧代码，仍然可用）"
  exit 1
fi

echo
echo "=== 3. 真的 import 一遍（py_compile 抓不到缺导入）==="
if $PY -c "
import sys
sys.path.insert(0, '$SITE')
import xishu_pipeline.routes as r
import xishu_pipeline.pipeline as p
import xishu_pipeline.resilience as res
print('  routes / pipeline / resilience 三个模块 import 成功')
print('  FAQ_CACHE =', type(res.FAQ_CACHE).__name__)
print('  /cache/stats 路由存在 =', any(getattr(x, 'path', '') == '/cache/stats' for x in r.app.routes))
print('  /doc/info 路由存在    =', any(getattr(x, 'path', '') == '/doc/info' for x in r.app.routes))
print('  /doc/text 路由存在    =', any(getattr(x, 'path', '') == '/doc/text' for x in r.app.routes))
"; then
  echo "  import 成功"
else
  echo "  import 失败，中止（不重启，线上还是旧代码，仍然可用）"
  exit 1
fi

echo
echo "=== 4. 重启（走安全重启，会归档旧日志）==="
OLD_PID=$(pgrep -f 'uvicorn.*8011' | head -1)
echo "  重启前 pid = ${OLD_PID:-无}"
bash "$RESTART"
sleep 6

echo
echo "=== 5. 验活 ==="
NEW_PID=$(pgrep -f 'uvicorn.*8011' | head -1)
echo "  重启后 pid = ${NEW_PID:-无}"
OK=1
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8011/ 2>/dev/null)
  if [ "$code" = "200" ]; then echo "  GET /        → 200（第 $i 次探测）"; OK=0; break; fi
  echo "  GET /        → $code，等 2 秒再试"
  sleep 2
done
[ "$OK" = "0" ] || { echo "  ★ 站点没有起来！"; exit 1; }

echo "  /health      → $(curl -s --max-time 5 http://127.0.0.1:8011/health)"
echo "  /cache/stats → $(curl -s --max-time 5 http://127.0.0.1:8011/cache/stats)"

echo
echo "=== 6. 前端静态文件是不是新的 ==="
echo "  index.html md5 线上 = $(md5sum "$SITE/frontend/index.html" | cut -c1-32)"
echo "  含 docText 元素 = $(grep -c 'id=\"docText\"' "$SITE/frontend/index.html")"
echo "  ask.js  含 friendlyError = $(grep -c 'function friendlyError' "$SITE/frontend/js/ask.js")"
echo "  message.js 含 /doc/info  = $(grep -c '/doc/info?source=' "$SITE/frontend/js/message.js")"
echo "  message.js 含 streaming  = $(grep -c 'm.streaming === true' "$SITE/frontend/js/message.js")"

echo
echo "部署完成。"
