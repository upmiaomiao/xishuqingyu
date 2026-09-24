#!/bin/bash
B=http://127.0.0.1:8011
echo "================ 最终验收 @ $(date -u +%H:%M:%S) UTC ================"

echo
echo "--- 1. 站点与各通路健康 ---"
echo "  /health      $(curl -s -m 10 $B/health | head -c 100)"
echo "  /kg/stats    $(curl -s -m 15 $B/kg/stats | head -c 80)"
echo "  /gen/api/health  $(curl -s -m 15 $B/gen/api/health | head -c 80)"
echo "  /audit/api/reports  $(curl -s -m 20 -o /dev/null -w '%{http_code}' $B/audit/api/reports)"

echo
echo "--- 2. 历史报告接口 ---"
echo "  列表份数：$(curl -s -m 20 $B/gen/api/outputs | grep -o '\"name\"' | wc -l)"
echo "  含今天(20260918)：$(curl -s -m 20 $B/gen/api/outputs | grep -c '20260918') 次（应为 0）"

echo
echo "--- 3. 归档/删除接口在位（用非法名探测，不碰真文件）---"
printf '  archive 非法名 -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST $B/gen/api/archive -H 'Content-Type: application/json' --data-binary '{"name":"x.txt"}')"
printf '  delete  非法名 -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST $B/gen/api/delete  -H 'Content-Type: application/json' --data-binary '{"name":"x.txt"}')"
printf '  archive 穿越名 -> %s\n' "$(curl -s -o /dev/null -w '%{http_code}' -m 20 -X POST $B/gen/api/archive -H 'Content-Type: application/json' --data-binary '{"name":"../../etc/passwd.docx"}')"

echo
echo "--- 4. 静态资源是新版 ---"
echo "  css 含 flex: none 卡片：$(curl -s -m 15 $B/gen/static/gen_ui.css | grep -c '右栏改为内部滚动后')"
echo "  css 含 ge-out-act    ：$(curl -s -m 15 $B/gen/static/gen_ui.css | grep -c 'ge-out-act')"
echo "  css 含 ge-foot       ：$(curl -s -m 15 $B/gen/static/gen_ui.css | grep -c 'ge-foot')（应为 0）"
echo "  js  含 归档按钮       ：$(curl -s -m 15 $B/gen/static/gen_ui.js | grep -c 'data-act=\"archive\"')"
echo "  js  含 彻底删除       ：$(curl -s -m 15 $B/gen/static/gen_ui.js | grep -c 'data-act=\"delete\"')"
echo "  js  含 二次确认       ：$(curl -s -m 15 $B/gen/static/gen_ui.js | grep -c '请再确认一次')"
echo "  js  含 ge-foot       ：$(curl -s -m 15 $B/gen/static/gen_ui.js | grep -c 'ge-foot')（应为 0）"

echo
echo "--- 5. 页面可达 ---"
for p in / /gen /audit; do
  printf '  %-8s %s  %s 字节\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 20 $B$p)" "$(curl -s -m 20 $B$p | wc -c)"
done
