#!/usr/bin/env bash
# 两阶段上线的"第一阶段"：用暂存 bundle 树建暂存索引。
# 线上索引与线上服务都不动。
set -euo pipefail
PY=/home/test/fagui_serve/.venv/bin/python
RAG=/data/fagui_rag
STAGE_TREE=$RAG/okf_bundles_stage
STAGE_INDEX=$RAG/index_stage

echo "==== 1) 暂存树与线上树对比"
echo "线上文档: $(find "$RAG/okf_bundles" -name '*.md' | wc -l)"
echo "暂存文档: $(find "$STAGE_TREE" -name '*.md' | wc -l)"
echo "线上字节: $(du -sh "$RAG/okf_bundles" | cut -f1)"
echo "暂存字节: $(du -sh "$STAGE_TREE" | cut -f1)"

echo
echo "==== 2) 建暂存索引"
cd "$RAG"
rm -rf "$STAGE_INDEX"
BUNDLE_ROOT="$STAGE_TREE" INDEX_DIR="$STAGE_INDEX" \
  "$PY" ingest_okf.py 2>&1 | tail -25

echo
echo "==== 3) 暂存索引与线上索引规模对比"
for d in "$RAG/index" "$STAGE_INDEX"; do
  n=$(wc -l < "$d/chunks.jsonl" 2>/dev/null || echo 0)
  sz=$(du -sh "$d" 2>/dev/null | cut -f1)
  echo "  $d: $n chunks, $sz"
done
