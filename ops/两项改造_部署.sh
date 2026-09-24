#!/bin/bash
# 两项改造（审核上传 + 图谱推荐词）—— 部署并重启。
#
# 前提：**先跑过 两项改造_备份.sh**。本脚本会检查备份目录，没备份就中止。
#
# 启动器是冻结的（md5 不得改动），所以这里只替换包内文件 + 调安全重启脚本，
# 绝不碰 launch_xishu_qingyu_qa_8011.sh。
set -u
SRC=/home/test/_上传暂存
S=/home/test/xishu_qingyu_serve
STAMP=$(cat /home/test/_重构归档_20260918/.last_stamp_两项 2>/dev/null || echo "")
BAK=/home/test/_重构归档_20260918/两项改造_前

echo "=== 0. 前置检查 ==="
if [ -z "$STAMP" ]; then
  echo "  ★ 没找到备份时间戳 —— 先跑 两项改造_备份.sh"
  exit 1
fi
echo "  备份时间戳：$STAMP"
# 逐个确认备份文件在位，缺一个都不往下走
need="xishu_pipeline_kg.py xishu_pipeline_routes.py xishu_pipeline_errors.py
xishu_pipeline_audit_routes.py xishu_pipeline_resilience.py
xishu_pipeline_static_audit_ui.js frontend_index.html frontend_app.css
frontend_js_kg.js frontend_js_views.js frontend_js_main.js"
miss=0
for f in $need; do
  if [ ! -f "$BAK/$f.$STAMP" ]; then
    echo "  ★ 备份缺：$f.$STAMP"
    miss=$((miss+1))
  fi
done
if [ "$miss" -gt 0 ]; then
  echo "  ★ 备份不完整（缺 $miss 个），中止。"
  exit 1
fi
echo "  备份 11 个文件齐全"

# 启动器必须原样存在 —— 上次 pkill + 错误启动器路径导致过一次事故
LAUNCH=$S/launch_xishu_qingyu_qa_8011.sh
if [ ! -f "$LAUNCH" ]; then
  echo "  ★ 启动器不存在：$LAUNCH —— 中止"
  exit 1
fi
echo "  启动器在位"

# 安全重启脚本
RESTART=/home/test/安全重启8011.sh
if [ ! -f "$RESTART" ]; then
  echo "  ★ 安全重启脚本不存在：$RESTART —— 中止"
  exit 1
fi
echo "  安全重启脚本在位"

echo
echo "=== 1. 记录改动前的指纹（回滚时对照用）==="
for f in xishu_pipeline/kg.py xishu_pipeline/resilience.py frontend/js/kg.js; do
  printf '  before %-32s %s\n' "$f" "$(md5sum "$S/$f" | cut -c1-12)"
done

echo
echo "=== 2. 替换文件 ==="
copy() {
  local rel="$1"
  local src="$SRC/$rel"
  local dst="$S/$rel"
  if [ ! -f "$src" ]; then
    echo "  ★ 暂存里没有 $rel"
    return 1
  fi
  mkdir -p "$(dirname "$dst")"
  cp -f "$src" "$dst"
  printf '  %-40s %8d B  %s\n' "$rel" "$(stat -c%s "$dst")" "$(md5sum "$dst" | cut -c1-12)"
  return 0
}
fail=0
for f in \
  xishu_pipeline/kg.py \
  xishu_pipeline/routes.py \
  xishu_pipeline/errors.py \
  xishu_pipeline/audit_routes.py \
  xishu_pipeline/resilience.py \
  xishu_pipeline/static/audit_ui.js \
  frontend/index.html \
  frontend/app.css \
  frontend/js/kg.js \
  frontend/js/views.js \
  frontend/js/main.js \
  ; do
  copy "$f" || fail=$((fail+1))
done
if [ "$fail" -gt 0 ]; then
  echo "  ★ 有 $fail 个文件没替换成功，中止（不做重启）"
  exit 1
fi

echo
echo "=== 3. 语法自检（在服务器上再查一遍，避免把语法错的代码重启上去）==="
PY=/home/test/fagui_serve/.venv/bin/python
for f in kg routes errors audit_routes resilience; do
  if $PY -c "import ast,sys; ast.parse(open('$S/xishu_pipeline/$f.py',encoding='utf-8').read())" 2>/dev/null; then
    echo "  OK   $f.py"
  else
    echo "  ★    $f.py 语法错 —— 立刻回滚，不重启"
    for g in xishu_pipeline_kg.py:kg xishu_pipeline_routes.py:routes \
             xishu_pipeline_errors.py:errors \
             xishu_pipeline_audit_routes.py:audit_routes \
             xishu_pipeline_resilience.py:resilience; do
      b=${g%%:*}; t=${g##*:}
      cp -f "$BAK/$b.$STAMP" "$S/xishu_pipeline/$t.py"
    done
    echo "  已回滚 Python 文件。"
    exit 1
  fi
done

echo
echo "=== 4. 安全重启 ==="
bash "$RESTART" 2>&1 | tail -12

echo
echo "=== 5. 起来了吗 ==="
sleep 3
for i in 1 2 3 4 5 6 7 8; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8011/ || echo 000)
  if [ "$code" = "200" ]; then break; fi
  echo "  等待中…（第 $i 次，HTTP $code）"
  sleep 3
done
echo "  GET /            -> $code"
echo "  GET /health      -> $(curl -s --max-time 5 http://127.0.0.1:8011/health | head -c 120)"
echo "  GET /kg/suggest  -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 'http://127.0.0.1:8011/kg/suggest?per_label=4')"
echo "  GET /audit/api/reports -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8011/audit/api/reports)"
echo "  /audit/static/audit_ui.js -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8011/audit/static/audit_ui.js)"
echo "  /static/js/kg.js -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8011/static/js/kg.js)"
echo "  pid = $(cat $S/qa_8011.pid 2>/dev/null)"

if [ "$code" != "200" ]; then
  echo
  echo "★ 站点没起来！回滚命令："
  echo "  for g in xishu_pipeline_kg.py:kg xishu_pipeline_routes.py:routes xishu_pipeline_errors.py:errors xishu_pipeline_audit_routes.py:audit_routes xishu_pipeline_resilience.py:resilience; do b=\${g%%:*}; t=\${g##*:}; cp -f $BAK/\$b.$STAMP $S/xishu_pipeline/\$t.py; done"
  echo "  cp -f $BAK/xishu_pipeline_static_audit_ui.js.$STAMP $S/xishu_pipeline/static/audit_ui.js"
  echo "  cp -f $BAK/frontend_index.html.$STAMP $S/frontend/index.html"
  echo "  cp -f $BAK/frontend_app.css.$STAMP $S/frontend/app.css"
  echo "  for g in kg:kg views:views main:main; do b=\${g%%:*}; t=\${g##*:}; cp -f $BAK/frontend_js_\$b.js.$STAMP $S/frontend/js/\$t.js; done"
  echo "  bash $RESTART"
  exit 1
fi
echo
echo "部署完成。"
