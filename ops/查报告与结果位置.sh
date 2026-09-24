#!/usr/bin/env bash
# 只读：找出 6 份报告 PDF 与已存审核结果的位置（写 A3 验证脚本要用）
set -u
echo "===== 1) 报告目录 ====="
for d in /data/eia_reports /data/eia_audit/_审核结果 /data/eia_audit/results /data/eia_audit; do
  test -d "$d" && echo "--- $d" && ls -1 "$d" | head -12
done
echo
echo "===== 2) PDF 清单（含大小）====="
find /data/eia_reports -maxdepth 2 -name '*.pdf' -printf '%10s  %p\n' 2>/dev/null | head -20
echo
echo "===== 3) 已存结果（json）====="
find /data/eia_audit -maxdepth 3 -name '*.json' -newermt '2026-09-15' -printf '%10s  %TY-%Tm-%Td %TH:%TM  %p\n' 2>/dev/null | head -20
echo
echo "===== 4) 审核项里含「废气污染物清单」的结果文件 ====="
grep -rl "废气污染物清单" /data/eia_audit --include='*.json' 2>/dev/null | head -10
