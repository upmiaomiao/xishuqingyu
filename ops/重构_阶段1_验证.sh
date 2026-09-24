#!/bin/bash
# 阶段 1 验证：备份 → 部署 routes.py → 重启 → 验静态路由 → 清理探针
set -e
D=/home/test/xishu_qingyu_serve
P=$D/xishu_pipeline
ARC=/home/test/_重构归档_20260918/阶段1前
FR=$D/frontend

echo "=========== 1.1 备份（放归档目录，不留在生产目录）==========="
mkdir -p "$ARC"
cp -p "$P/routes.py" "$ARC/routes.py"
echo "  备份 $(md5sum "$ARC/routes.py" | cut -d' ' -f1)  -> $ARC/routes.py"
echo "  部署前线上 md5：$(md5sum "$P/routes.py" | cut -d' ' -f1)"

echo
echo "=========== 1.2 重启 ==========="
bash $D/launch_xishu_qingyu_qa_8011.sh stop >/dev/null 2>&1 || true
OLD=$(cat $D/qa_8011.pid 2>/dev/null || true)
for i in $(seq 1 20); do kill -0 "$OLD" 2>/dev/null || break; sleep 1; done
kill -0 "$OLD" 2>/dev/null && { kill -9 "$OLD"; sleep 2; }
bash $D/launch_xishu_qingyu_qa_8011.sh start
for i in $(seq 1 90); do
  curl -fsS -m 3 http://127.0.0.1:8011/health >/dev/null 2>&1 && { echo "  第 ${i}s /health 通"; break; }
  sleep 1
done
echo "  部署后线上 md5：$(md5sum "$P/routes.py" | cut -d' ' -f1)"

echo
echo "=========== 1.3 静态路由：白名单外必须 404 ==========="
for n in 'nope.css' 'index.html' 'app.css.bak' '../../etc/passwd' 'gen_ui.css'; do
  code=$(curl -s -o /tmp/r.txt -w '%{http_code}' -m 15 "http://127.0.0.1:8011/static/$n")
  printf '  %-22s -> %s  %s\n' "$n" "$code" "$(head -c 50 /tmp/r.txt)"
done

echo
echo "=========== 1.4 白名单内：真放一个文件，必须能取到 ==========="
printf 'body{color:#123456}\n' > "$FR/app.css"
code=$(curl -s -o /tmp/r.txt -w '%{http_code}' -m 15 http://127.0.0.1:8011/static/app.css)
ctype=$(curl -s -o /dev/null -w '%{content_type}' -m 15 http://127.0.0.1:8011/static/app.css)
cache=$(curl -s -D - -o /dev/null -m 15 http://127.0.0.1:8011/static/app.css | grep -i 'cache-control' | tr -d '\r')
printf '  app.css -> %s  content-type=%s\n' "$code" "$ctype"
printf '  正文：%s\n' "$(cat /tmp/r.txt)"
printf '  %s\n' "$cache"

printf 'window.__probe=1;\n' > "$FR/app.js"
code=$(curl -s -o /dev/null -w '%{http_code}' -m 15 http://127.0.0.1:8011/static/app.js)
ctype=$(curl -s -o /dev/null -w '%{content_type}' -m 15 http://127.0.0.1:8011/static/app.js)
printf '  app.js  -> %s  content-type=%s\n' "$code" "$ctype"

echo
echo "=========== 1.5 清理探针（不留垃圾）==========="
rm -f "$FR/app.css" "$FR/app.js"
echo "  frontend/ 现在：$(ls -1 "$FR" | tr '\n' ' ')"

echo
echo "=========== 1.6 原有通路无退化 ==========="
for p in / /gen /audit /health /kg/stats /audit/api/reports /gen/api/outputs; do
  printf '  %-22s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 20 http://127.0.0.1:8011$p)"
done
echo "  首页字节数：$(curl -s -m 20 http://127.0.0.1:8011/ | wc -c)（拆分前应为 41132）"
echo "  生成页列表份数：$(curl -s -m 20 http://127.0.0.1:8011/gen/api/outputs | grep -o '"name"' | wc -l)"
