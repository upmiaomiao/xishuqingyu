#!/bin/bash
# 只读：服务器上有没有能跑无头浏览器的东西（有的话就做真实的页面冒烟测试）
set -u
echo "=== 命令 ==="
for c in chromium chromium-browser google-chrome google-chrome-stable node nodejs npx firefox; do
  printf '%-24s %s\n' "$c" "$(command -v $c || echo -)"
done
echo
echo "=== python 侧 ==="
/home/test/fagui_serve/.venv/bin/pip list 2>/dev/null | grep -iE 'playwright|selenium|pyppeteer|requests-html' || echo "  无"
echo
echo "=== 有没有预装的浏览器二进制 ==="
ls -d /root/.cache/ms-playwright /home/test/.cache/ms-playwright 2>/dev/null || echo "  无 ms-playwright"
