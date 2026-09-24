#!/usr/bin/env bash
# 最终校验：回归基线 + 重复率 + 引用去重分布 + 检索命中
set -u
PY=/home/test/fagui_serve/.venv/bin/python
STAGE=/data/fagui_rag/okf_bundles_stage
BUNDLE=/data/fagui_rag/okf_bundles

echo "==== 1) 回归基线（影子 8012）"
cd /tmp && $PY /tmp/网站_回归基线.py --base http://127.0.0.1:8012 2>&1 | tail -4

echo
echo "==== 2) 补录重复率"
python3 /tmp/量重复率.py /tmp/repair_batch1.json "$BUNDLE" "$STAGE" 2>&1 | head -4

echo
echo "==== 3) 索引规模对比"
for d in /data/fagui_rag/index /data/fagui_rag/index_stage; do
  echo "  $d: $(wc -l < $d/chunks.jsonl) chunks, $(du -sh $d | cut -f1)"
done

echo
echo "==== 4) 引用去重：同一文件在引用里最多占几条"
export RAG_INDEX_DIR=/data/fagui_rag/index_stage
for q in "生活垃圾焚烧排污许可证申请与核发技术规范主要规定了哪些内容？" \
         "一般工业固体废物贮存场 I 类场的防渗要求是什么？"; do
  echo "-- $q"
  $PY /tmp/查检索结果.py "$q" --top-k 5 2>&1 | grep -v -e warning -e deprecat \
    | grep -e "^\[" -e "rerank=" | head -12
done
