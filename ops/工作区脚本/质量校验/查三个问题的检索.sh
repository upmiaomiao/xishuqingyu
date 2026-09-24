#!/usr/bin/env bash
# 对三个"内容已在库、但答不出"的问题，看检索到底取到了什么
PY=/home/test/fagui_serve/.venv/bin/python
export RAG_INDEX_DIR=/data/fagui_rag/index_stage

q1="储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？"
q2="制糖工业水污染物排放标准 GB 21909-2008 规定的水污染物排放限值是多少？"
q3="一般工业固体废物贮存场 I 类场的防渗要求是什么？"

for q in "$q1" "$q2" "$q3"; do
  echo "################################################################"
  $PY /tmp/查检索结果.py "$q" --top-k 4 2>&1 | grep -v -e warning -e deprecat
done
