#!/bin/bash
# 把回归测试跑出来的产物移进 _站点测试产物/（归档不删）。
# 判据用**文件名里的日期**（-20260918-），比 mtime 可靠：
# 产物可能被后续操作 touch 过，而文件名是生成时写死的。
set -e
OUT=/data/eia_report_gen/_生成结果
ARC="$OUT/_站点测试产物"
mkdir -p "$ARC"

BEFORE_TOP=$(ls "$OUT"/*.docx 2>/dev/null | wc -l)
BEFORE_ARC=$(ls "$ARC" 2>/dev/null | wc -l)

echo "=========== 归档回归测试产物（09-18）==========="
echo "  归档前：顶层 $BEFORE_TOP 份，_站点测试产物 $BEFORE_ARC 份"
echo

n=0
for f in "$OUT"/*20260918-*.docx; do
  [ -f "$f" ] || continue
  mv -n "$f" "$ARC/"
  n=$((n+1))
done

AFTER_TOP=$(ls "$OUT"/*.docx 2>/dev/null | wc -l)
AFTER_ARC=$(ls "$ARC" 2>/dev/null | wc -l)
echo "  本次移入 $n 份"
echo "  归档后：顶层 $AFTER_TOP 份，_站点测试产物 $AFTER_ARC 份"
echo

echo "  顶层剩余（应全是 09-17 的旧测试产物）："
ls -l --time-style=+%m-%d "$OUT"/*.docx 2>/dev/null | awk '{print $6}' | sort | uniq -c | sed 's/^/    /'
echo
echo "  顶层剩余的来源分布："
ls "$OUT"/*.docx 2>/dev/null | sed 's#.*/##' | sed 's/-报告表草稿.*//' | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /'
