#!/bin/bash
D=/home/test/xishu_qingyu_serve
echo "=== 1. 上传文件 md5（应与本地一致）==="
md5sum "$D/frontend/index.html" "$D/xishu_pipeline/routes.py"
md5sum "$D"/frontend/js/*.js

echo
echo "=== 2. index.html 结构 ==="
echo "  字节：$(stat -c%s "$D/frontend/index.html")  行数：$(wc -l < "$D/frontend/index.html")"
echo "  script 标签："
grep -o '<script[^>]*>' "$D/frontend/index.html" | sed 's/^/    /'
echo "  link 标签："
grep -o '<link[^>]*>' "$D/frontend/index.html" | sed 's/^/    /'
echo "  内联 script 数（应为 0）：$(grep -c '<script[^>]*>[^<]' "$D/frontend/index.html" || true)"
echo "  内联 style 数（应为 0）：$(grep -c '<style' "$D/frontend/index.html" || true)"

echo
echo "=== 3. js 目录 ==="
ls -l "$D/frontend/js/" | tail -n +2 | awk '{printf "  %7s  %s\n",$5,$9}'

echo
echo "=== 4. 重启脚本是否存在（必须先存日志，因为启动脚本用 > 会截断）==="
ls -l /home/test/安全重启8011.sh 2>/dev/null || echo "  没有安全重启脚本"
grep -n 'LOG_FILE' /home/test/xishu_qingyu_serve/launch_xishu_qingyu_qa_8011.sh 2>/dev/null | head -5

echo
echo "=== 5. 当前进程 ==="
ps -ef | grep -E 'xishu_qingyu_qa.*8011' | grep -v grep | sed 's/^/  /'
echo "  8011 监听："
ss -ltnp 2>/dev/null | grep ':8011' | sed 's/^/  /'
