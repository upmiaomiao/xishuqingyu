#!/usr/bin/env bash
# B 步全量：599 份环评报告 → OKF → 全量重建索引（含备份）
set -u
R=/data/fagui_rag
PY=/home/test/fagui_serve/.venv/bin/python
TOOLS=$R/.venv_tools/bin/python
TS=bak_before_eia_reports_20260916

echo "==== 1) 备份 index 与 okf_bundles ===="
if [ -d "$R/index.$TS" ]; then echo "已存在 $R/index.$TS"; else cp -a "$R/index" "$R/index.$TS" && echo "已备份 $R/index.$TS"; fi
if [ -d "$R/okf_bundles.$TS" ]; then echo "已存在 $R/okf_bundles.$TS"; else cp -a "$R/okf_bundles" "$R/okf_bundles.$TS" && echo "已备份 $R/okf_bundles.$TS"; fi
df -h /data | tail -1

echo
echo "==== 2) 全量转换（跳过错文/空文） ===="
$TOOLS /tmp/环评报告转OKF.py --src "$R/eia_reports_raw" --bundle "$R/okf_bundles" 2>&1 | tail -20

echo
echo "==== 3) 入库后 bundle 规模 ===="
echo "线上 md 总数: $(find "$R/okf_bundles" -name '*.md' | wc -l)"
echo "环评报告 md : $(find "$R/okf_bundles/环评报告" -name '*.md' | wc -l)"
du -sh "$R/okf_bundles" "$R/okf_bundles/环评报告"

echo
echo "==== 4) 全量重建索引 ===="
cd "$R"
$PY -u ingest_okf.py 2>&1 | tail -14
