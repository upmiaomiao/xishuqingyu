#!/usr/bin/env bash
# 服务器 RAG 库现状盘点
R=/data/fagui_rag
echo "== live index =="
wc -l < "$R/index/chunks.jsonl"
echo "== live bundle md count =="
find "$R/okf_bundles" -name '*.md' | wc -l
echo "== bundles size =="
du -sh "$R/okf_bundles" "$R/index"
echo "== backups =="
ls -d "$R"/index.bak* "$R"/okf_bundles.bak* 2>/dev/null
echo "== index meta =="
cat "$R/index/meta.json"
echo
echo "== health 8011 =="
curl -fsS http://127.0.0.1:8011/health
echo
echo "== health 8012 (shadow, P6) =="
curl -fsS http://127.0.0.1:8012/health 2>/dev/null || echo "(8012 not running)"
echo
echo "== ingest/retriever md5 =="
md5sum "$R/ingest_okf.py" "$R/retriever.py"
