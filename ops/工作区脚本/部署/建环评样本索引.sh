#!/usr/bin/env bash
# 环评报告语料：小样本验证（不动线上索引与线上 bundle）
set -u
R=/data/fagui_rag
PY=/home/test/fagui_serve/.venv/bin/python
TOOLS=$R/.venv_tools/bin/python
SAMPLE=$R/okf_bundles_eia_sample
SIDX=$R/index_eia_sample

echo "== 0) 已上传的原始 md =="
ls "$R/eia_reports_raw" | wc -l
du -sh "$R/eia_reports_raw"

echo
echo "== 1) 暂存 bundle 树 = 线上副本 =="
rm -rf "$SAMPLE"
cp -a "$R/okf_bundles" "$SAMPLE"
echo "线上 md 数: $(find "$R/okf_bundles" -name '*.md' | wc -l)  暂存 md 数: $(find "$SAMPLE" -name '*.md' | wc -l)"

echo
echo "== 2) 转换 12 份样本 =="
$TOOLS /tmp/环评报告转OKF.py --src "$R/eia_reports_raw" --bundle "$SAMPLE" --limit 12 2>&1 | tail -26

echo
echo "== 3) 建样本索引 =="
cd "$R"
BUNDLE_ROOT="$SAMPLE" INDEX_DIR="$SIDX" $PY -u ingest_okf.py 2>&1 | tail -6
