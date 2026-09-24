#!/usr/bin/env bash
# 重建暂存树并重跑批次一 + 关键文档（表格单独入库版）
set -u
PY=/data/fagui_rag/.venv_tools/bin/python
BUNDLE=/data/fagui_rag/okf_bundles
STAGE=/data/fagui_rag/okf_bundles_stage

echo "==== 1) 从线上 bundle 重建暂存树（丢弃上一轮结果，避免叠加）"
rm -rf "$STAGE"
cp -a "$BUNDLE" "$STAGE"
echo "暂存树: $(find "$STAGE" -name '*.md' | wc -l) 份 / $(du -sh "$STAGE" | cut -f1)"

echo
echo "==== 2) 批次一：缺口 >= 1500 字"
$PY /tmp/语料正文回填.py repair --targets /tmp/回填清单.json --stage "$STAGE" \
  --report /tmp/repair_batch1.json --min-gap 1500 --free-search \
  2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated | tail -12

echo
echo "==== 3) 关键业务文档（可能不在批次一内，单独补）"
for kw in "国家危险废物名录" "储油库大气污染物排放标准（GB 20950—2020" \
          "制糖工业水污染物排放标准（GB 21909-2008" \
          "一般工业固体废物贮存和填埋污染控制标准 GB 18599" \
          "海水水质标准 GB 3097-1997"; do
  $PY /tmp/语料正文回填.py repair --targets /tmp/回填清单.json --stage "$STAGE" \
    --report /tmp/repair_keys.json --free-search --match "$kw" \
    2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated \
    | grep -e "待处理" -e "回填槽位" -e "表格还原"
done

echo
echo "==== 4) 重复率检查"
python3 /tmp/量重复率.py /tmp/repair_batch1.json "$BUNDLE" "$STAGE" 2>&1 | head -8
