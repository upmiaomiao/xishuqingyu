#!/bin/bash
# 清理验收副本及其全部派生文件（副本是我 03:53 自己造的，不是用户报告）。
# 逐项列出删了什么、剩了什么，避免"悄悄删了东西"。
set -u
SHA=e49e8518e74669aa51a7ac229b0d8d7ad5ce8620     # 副本自己的 sha1（缓存/页图按它分目录）
NAME="_验收副本_临沂"
echo "=== 删之前存在的 ==="
ls -l "/data/eia_reports/$NAME.pdf" 2>/dev/null
ls -l "/data/eia_audit/_审核结果/$NAME.json" 2>/dev/null
ls -ld "/data/eia_audit/_cache/$SHA.json" 2>/dev/null
ls -ld "/data/eia_audit/_审核结果/页图/$SHA" 2>/dev/null && du -sh "/data/eia_audit/_审核结果/页图/$SHA"

rm -f "/data/eia_reports/$NAME.pdf"
rm -f "/data/eia_audit/_审核结果/$NAME.json"
rm -f "/data/eia_audit/_cache/$SHA.json"
rm -rf "/data/eia_audit/_审核结果/页图/$SHA"

echo
echo "=== 删之后 ==="
for p in "/data/eia_reports/$NAME.pdf" "/data/eia_audit/_审核结果/$NAME.json" "/data/eia_audit/_cache/$SHA.json" "/data/eia_audit/_审核结果/页图/$SHA"; do
  if [ -e "$p" ]; then echo "仍在: $p"; else echo "已删: $p"; fi
done
echo
echo "=== 报告清单（应回到 8 份）==="
ls /data/eia_reports/*.pdf | wc -l
echo "=== 审核结果（应为 6 份，都是正式报告）==="
ls /data/eia_audit/_审核结果/*.json 2>/dev/null | wc -l
ls /data/eia_audit/_审核结果/*.json 2>/dev/null
