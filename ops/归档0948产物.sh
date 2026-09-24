#!/bin/bash
# 归档那份 09:48 的测试产物（归档不删除），并核对最终状态
OUT=/data/eia_report_gen/_生成结果
ARC=$OUT/_站点测试产物
mkdir -p "$ARC"

echo "=========== 归档 09:48 那份（已证实来自单测样本）==========="
for f in "$OUT"/*20260918-094828*.docx; do
  [ -f "$f" ] || continue
  echo "  $(basename "$f")"
  mv "$f" "$ARC/"
done

echo
echo "=========== 现状 ==========="
echo "  顶层 .docx：$(ls $OUT/*.docx 2>/dev/null | wc -l) 份"
for d in "$OUT"/_*; do [ -d "$d" ] && echo "  $(basename "$d")：$(ls "$d" | wc -l) 个"; done

echo
echo "=========== 顶层剩下的 09-17 草稿（迁移前就在，属遗留测试产物）==========="
ls -1 $OUT/*20260917*.docx 2>/dev/null | wc -l | sed 's/^/  带 20260917 的：/'
ls -1 $OUT/*.docx 2>/dev/null | sed 's#.*/##' | sed 's/-报告表草稿.*//' | sort | uniq -c | sort -rn | head -8 | sed 's/^/    /'

echo
echo "=========== 日志保全机制就位 ==========="
ls -la /home/test/_重构归档_20260918/日志/ 2>/dev/null | sed 's/^/  /' || echo "  （首次运行后才有）"
