#!/bin/bash
# 查 C7/B4 的数据现状：江苏地标 DB32/1072 与 GB18918 到底在不在语料里。只读。
cd /data/fagui_rag/okf_bundles || exit 1
echo "=== 语料里各关键词命中的文件数 ==="
for k in "DB32" "1072" "太湖" "GB18918" "江苏"; do
  n=$(grep -rl -- "$k" . 2>/dev/null | wc -l)
  echo "  $k : $n"
done
echo
echo "=== 有没有以它们命名的 bundle 目录 ==="
find . -maxdepth 4 -type d \( -name "*DB32*" -o -name "*江苏*" -o -name "*太湖*" \) 2>/dev/null | head -8
echo
echo "=== 索引里（chunks.jsonl）标题/正文含 DB32 的行数 ==="
if [ -f /data/fagui_rag/index/chunks.jsonl ]; then
  grep -c "DB32" /data/fagui_rag/index/chunks.jsonl
else
  ls /data/fagui_rag/index | head -5
fi
