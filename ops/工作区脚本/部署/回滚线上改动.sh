#!/usr/bin/env bash
# 回滚：把检索/入库改动从线上路径撤下（线上完全被动），新版本另存备查。
# 影子实例 8012 已把新代码载入内存，继续可用；重启影子用 /tmp/起影子_p6.sh。
set -u
RAG=/data/fagui_rag
TS=p6_20260916

echo "==== 1) 保存新版本（不丢改动）"
cp -n "$RAG/retriever.py" "$RAG/retriever.py.$TS" 2>/dev/null || true
cp -n "$RAG/ingest_okf.py" "$RAG/ingest_okf.py.$TS" 2>/dev/null || true
ls -la "$RAG/retriever.py.$TS" "$RAG/ingest_okf.py.$TS"

echo
echo "==== 2) 线上路径恢复为改动前版本"
cp "$RAG/retriever.py.bak_20260916" "$RAG/retriever.py"
cp "$RAG/ingest_okf.py.bak_before_ctx_20260916" "$RAG/ingest_okf.py"

echo "retriever.py  md5: $(md5sum "$RAG/retriever.py" | cut -d' ' -f1)"
echo "  期望(=备份)   : $(md5sum "$RAG/retriever.py.bak_20260916" | cut -d' ' -f1)"
echo "ingest_okf.py md5: $(md5sum "$RAG/ingest_okf.py" | cut -d' ' -f1)"
echo "  期望(=备份)   : $(md5sum "$RAG/ingest_okf.py.bak_before_ctx_20260916" | cut -d' ' -f1)"

echo
echo "==== 3) 线上 8011 健康与索引（应完全未变）"
curl -fsS http://127.0.0.1:8011/health; echo
echo "线上索引 chunks: $(wc -l < $RAG/index/chunks.jsonl)"
echo "线上索引 mtime : $(stat -c %y $RAG/index/chunks.jsonl)"

echo
echo "==== 4) 影子实例 8012 仍可服务（内存中是 P6 代码）"
curl -fsS http://127.0.0.1:8012/health; echo

cat > /tmp/起影子_p6.sh <<'EOS'
#!/usr/bin/env bash
# 影子实例（含 P6 检索改动）启动：临时换上新版 → 起 → 立刻还原线上版本。
# 影子在启动时把模块读进内存，所以之后再还原不影响它运行。
set -u
RAG=/data/fagui_rag
PORT=${1:-8012}
cp "$RAG/retriever.py" "$RAG/retriever.py.live_tmp"
cp "$RAG/retriever.py.p6_20260916" "$RAG/retriever.py"
fuser -k -n tcp "$PORT" >/dev/null 2>&1 || true
sleep 2
bash /tmp/起影子.sh "$RAG/index_stage" "$PORT"
cp "$RAG/retriever.py.live_tmp" "$RAG/retriever.py"
rm -f "$RAG/retriever.py.live_tmp"
echo "线上版本已还原: $(md5sum "$RAG/retriever.py" | cut -d' ' -f1)"
EOS
chmod +x /tmp/起影子_p6.sh
echo "已生成 /tmp/起影子_p6.sh"
