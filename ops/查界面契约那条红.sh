#!/usr/bin/env bash
# 只读：这条红是不是我改出来的 —— 在"改动前的备份"里找这两个字段名。
set -u
BAK=/home/test/_重构归档_20260922/第一批_前
echo "=== 备份目录 ==="
ls -la "$BAK" | head

echo
echo "=== 改动前的 audit_ui.js 里有没有 已审核 / 汇总页 ==="
grep -n "已审核" "$BAK/audit_ui.js.20260922_074612" | head -3
grep -n "汇总页" "$BAK/audit_ui.js.20260922_074612" | head -3
echo "(以上为空 = 改动前没有；有行 = 改动前就有 → 这条红是原有的)"

echo
echo "=== 后端谁产出这两个字段（在站点代码里找）==="
grep -rn "已审核" /home/test/xishu_qingyu_serve/xishu_pipeline/*.py | head -4
grep -rn "汇总页" /home/test/xishu_qingyu_serve/xishu_pipeline/*.py | head -4

echo
echo "=== 接口实际返回（只看字段名）==="
curl -s "http://127.0.0.1:8011/audit/api/reports" | head -c 300; echo
