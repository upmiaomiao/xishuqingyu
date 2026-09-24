#!/usr/bin/env bash
# P6 上线：语料（表格回填）+ ingest（表格单独成块/来源抬头）+ 新索引 index_p6 一起切。
#
# 为什么三样要一起切：
#   · index_p6 是用"回填后的语料 + P6 版 ingest"建出来的，三者必须一致；
#   · 只切索引不切语料，将来任何一次"按语料重建"都会把回填成果丢掉；
#   · 只切语料不切 ingest，下次重建又会切回"表格混在散文块里"。
#
# 回滚命令（脚本会再打印一次）：
#   mv /data/fagui_rag/index /data/fagui_rag/index_p6_回滚留档
#   mv /data/fagui_rag/index.bak_before_P6_<TS> /data/fagui_rag/index
#   mv /data/fagui_rag/okf_bundles /data/fagui_rag/okf_bundles_p6_回滚留档
#   mv /data/fagui_rag/okf_bundles.bak_before_P6_<TS> /data/fagui_rag/okf_bundles
#   cp /data/fagui_rag/ingest_okf.py.bak_before_P6_<TS> /data/fagui_rag/ingest_okf.py
#   bash /home/test/安全重启8011.sh
set -u
RAG=/data/fagui_rag
TS=$(date +%Y%m%d_%H%M%S)
PKG=/home/test/_重构归档_20260922/P6_前

echo "===== 0) 前置检查 ====="
for f in "$RAG/index/chunks.jsonl" "$RAG/index_p6/chunks.jsonl" "$RAG/index_p6/vectors.npy" \
         "$RAG/okf_bundles" "$RAG/okf_bundles_p6" "$RAG/ingest_okf.py.p6_20260916"; do
  [ -e "$f" ] || { echo "❌ 缺 $f，停"; exit 1; }
done
echo "  线上块数：$(wc -l < "$RAG/index/chunks.jsonl")"
echo "  新索引块数：$(wc -l < "$RAG/index_p6/chunks.jsonl")"
echo "  回填语料 md 数：$(find "$RAG/okf_bundles_p6" -name '*.md' | wc -l)"
echo "  线上语料 md 数：$(find "$RAG/okf_bundles" -name '*.md' | wc -l)"
mkdir -p "$PKG"

echo
echo "===== 1) 备份 ingest_okf.py（线上版另存）====="
cp -p "$RAG/ingest_okf.py" "$RAG/ingest_okf.py.bak_before_P6_$TS"
cp -p "$RAG/ingest_okf.py" "$PKG/ingest_okf.py.$TS"
echo "  线上版 $(md5sum "$RAG/ingest_okf.py" | cut -d' ' -f1) → ingest_okf.py.bak_before_P6_$TS"

echo
echo "===== 2) 停影子实例（它指着 index_p6 与 okf_bundles_p6，切走后就没用了）====="
fuser -k -n tcp 8013 2>/dev/null && echo "  8013 已停" || echo "  8013 本来就没在跑"

echo
echo "===== 3) 语料切换（先备份线上语料，两次 mv 紧挨着）====="
mv "$RAG/okf_bundles" "$RAG/okf_bundles.bak_before_P6_$TS"
mv "$RAG/okf_bundles_p6" "$RAG/okf_bundles"
echo "  线上语料 → okf_bundles.bak_before_P6_$TS"
echo "  回填语料 → okf_bundles（$(find "$RAG/okf_bundles" -name '*.md' | wc -l) 份）"

echo
echo "===== 4) ingest 换成 P6 版 ====="
cp -p "$RAG/ingest_okf.py.p6_20260916" "$RAG/ingest_okf.py"
echo "  现在 ingest_okf.py = $(md5sum "$RAG/ingest_okf.py" | cut -d' ' -f1)（P6 版应为 6a0a1ea84b9c171bd4d898bc001e9faa）"

echo
echo "===== 5) 索引切换（切前自检 + 归档旧索引 + 重启 8011 + 健康检查）====="
bash /home/test/切换索引.sh "$RAG/index_p6" 2>&1 | tail -22

echo
echo "===== 6) 上线后验证 ====="
curl -fsS --max-time 8 http://127.0.0.1:8011/health && echo
grep -a "Retriever" /home/test/xishu_qingyu_serve/qa_8011.log | tail -2
echo "  审核页 /audit/api/reports → $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8011/audit/api/reports)"
echo "  生成页 /gen/list → $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8011/gen/list)"

echo
echo "===== 回滚（如需）====="
echo "  mv $RAG/index $RAG/index_p6_回滚留档_$TS"
echo "  mv $RAG/index.bak_before_标准与标题_* $RAG/index     # 取上一步打印的那个备份目录"
echo "  mv $RAG/okf_bundles $RAG/okf_bundles_p6_回滚留档_$TS"
echo "  mv $RAG/okf_bundles.bak_before_P6_$TS $RAG/okf_bundles"
echo "  cp $RAG/ingest_okf.py.bak_before_P6_$TS $RAG/ingest_okf.py"
echo "  bash /home/test/安全重启8011.sh"
