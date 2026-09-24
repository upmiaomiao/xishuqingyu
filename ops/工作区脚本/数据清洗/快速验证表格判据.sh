#!/usr/bin/env bash
# 只重跑关键文档（快速验证表格数值判据是否生效），不重建整棵树
set -u
PY=/data/fagui_rag/.venv_tools/bin/python
BUNDLE=/data/fagui_rag/okf_bundles
STAGE=/data/fagui_rag/okf_bundles_stage

echo "==== 从线上重建这两份文档的暂存副本（保证从干净状态测）"
for kw in "储油库大气污染物排放标准（GB 20950—2020" "制糖工业水污染物排放标准（GB 21909-2008"; do
  $PY - "$BUNDLE" "$STAGE" "$kw" <<'PYEOF'
import os, shutil, sys
bundle, stage, kw = sys.argv[1], sys.argv[2], sys.argv[3]
n = 0
for dp, _dn, fn in os.walk(bundle):
    for f in fn:
        if f.endswith(".md") and kw in f:
            src = os.path.join(dp, f)
            dst = os.path.join(stage, os.path.relpath(src, bundle))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
print(f"  重置 {n} 份: {kw[:36]}")
PYEOF
done

echo
echo "==== 重跑这两份"
for kw in "储油库大气污染物排放标准（GB 20950—2020" "制糖工业水污染物排放标准（GB 21909-2008"; do
  $PY /tmp/语料正文回填.py repair --targets /tmp/回填清单.json --stage "$STAGE" \
    --report /tmp/repair_keys.json --free-search --match "$kw" \
    2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated | grep -e "待处理" -e "回填槽位"
done

echo
echo "==== 储油库：限值表"
F=$(grep -rl "储油库大气污染物排放标准（GB 20950—2020" "$STAGE" --include=*.md | head -1)
echo "markdown 表格数: $(grep -c -- '| --- |' "$F")"
grep -n -e "NMHC" -e "处理效率" "$F" | tail -6
