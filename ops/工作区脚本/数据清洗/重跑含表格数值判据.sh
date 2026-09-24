#!/usr/bin/env bash
# 用新的"表格数值判据"重跑批次一 + 关键文档，并检查储油库限值表是否入库
set -u
PY=/data/fagui_rag/.venv_tools/bin/python
BUNDLE=/data/fagui_rag/okf_bundles
STAGE=/data/fagui_rag/okf_bundles_stage

echo "==== 1) 重建暂存树"
rm -rf "$STAGE"; cp -a "$BUNDLE" "$STAGE"

echo "==== 2) 批次一（缺口 >= 1500）"
$PY /tmp/语料正文回填.py repair --targets /tmp/回填清单.json --stage "$STAGE" \
  --report /tmp/repair_batch1.json --min-gap 1500 --free-search \
  2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated | tail -10

echo
echo "==== 3) 关键业务文档"
for kw in "国家危险废物名录" "储油库大气污染物排放标准（GB 20950—2020" \
          "制糖工业水污染物排放标准（GB 21909-2008" \
          "一般工业固体废物贮存和填埋污染控制标准 GB 18599" \
          "海水水质标准 GB 3097-1997"; do
  echo "-- $kw"
  $PY /tmp/语料正文回填.py repair --targets /tmp/回填清单.json --stage "$STAGE" \
    --report /tmp/repair_keys.json --free-search --match "$kw" \
    2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated \
    | grep -e "待处理" -e "回填槽位"
done

echo
echo "==== 4) 储油库限值表是否入库"
F=$(grep -rl "储油库大气污染物排放标准（GB 20950—2020" "$STAGE" --include=*.md | head -1)
echo "file: $(basename "$F")"
echo "markdown 表格数: $(grep -c -- '| --- |' "$F")"
grep -n "NMHC" "$F" | tail -3
