#!/usr/bin/env bash
# 只读：把入库配方 make_embed_text 的真实实现打出来，确认 status 到底进不进嵌入文本。
set -u
F=/data/fagui_rag/ingest_okf.py
L=$(grep -n 'def make_embed_text' "$F" | head -1 | cut -d: -f1)
echo "===== make_embed_text（第 $L 行起）====="
sed -n "${L},$((L + 18))p" "$F"

echo
echo "===== 该函数体里有没有 status / issuer / region 这些元数据 ====="
sed -n "${L},$((L + 18))p" "$F" | grep -n 'status\|issuer\|region\|tags' || echo "  （一个都没有 → status 变更不需要重嵌）"

echo
echo "===== 对比：入库时写进元数据的字段（第 185-200 行）====="
sed -n '185,200p' "$F"
