#!/usr/bin/env bash
# 全量入库后状态检查
R=/data/fagui_rag
echo "== index files =="
ls -la "$R/index/"
echo "chunks: $(wc -l < "$R/index/chunks.jsonl")"
cat "$R/index/meta.json"
echo
echo "== 8011 =="
curl -fsS -m 10 http://127.0.0.1:8011/health || echo "(无响应)"
echo
echo "== 8011 log tail =="
tail -6 /home/test/xishu_qingyu_serve/qa_8011.log
echo
echo "== 进程与内存 =="
pgrep -af xishu_qingyu_qa | head -4
for p in $(pgrep -f xishu_qingyu_qa); do
  ps -o pid=,etime=,rss=,cmd= -p "$p" | cut -c1-140
done
echo
echo "== 端口 =="
ss -ltnp 2>/dev/null | grep -e ':8011' -e ':8012'
echo
echo "== 备份 =="
ls -d "$R"/index.bak* "$R"/okf_bundles.bak* 2>/dev/null
df -h /data | tail -1
