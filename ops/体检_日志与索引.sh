#!/bin/bash
# 站点日志里的 rerank 失败量化 + 线上索引版本
LOG=/home/test/xishu_qingyu_serve/qa_8011.log
echo "=== 日志规模 ==="
wc -l $LOG | awk '{print "  行数 "$1}'
ls -la --time-style=+%F_%T $LOG | awk '{print "  大小 "$5"  改于 "$6}'
echo
echo "=== 日志时间跨度（首/末行时间戳）==="
head -3 $LOG | sed 's/^/  /'
tail -2 $LOG | sed 's/^/  /'
echo
echo "=== rerank 失败次数 ==="
grep -c "rerank failed" $LOG
echo "  —— 按错误类型 ——"
grep "rerank failed" $LOG | sed 's/.*rerank failed (\([^)]*\)).*/\1/' | sort | uniq -c | sort -rn | head
echo
echo "=== 最近 3 次失败的上下文 ==="
grep -n "rerank failed" $LOG | tail -3 | sed 's/^/  /'
echo
echo "=== 全部失败行的时间（前后各取上下文里的时间戳）==="
grep -B1 "rerank failed" $LOG | grep -oE '^[0-9]{2}:[0-9]{2}:[0-9]{2}|[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}' | tail -6 | sed 's/^/  /'
echo
echo "=== 站点处理过的请求量（按关键日志行统计）==="
for k in "FAQ" "cache hit" "Retriever" "rerank" "route=" "500" "Traceback"; do
  printf "  %-12s %s\n" "$k" "$(grep -c "$k" $LOG)"
done
echo
echo "=== 线上索引是哪一版 ==="
ls -la --time-style=+%F_%T /data/fagui_rag/index/meta.json /data/fagui_rag/index/chunks.jsonl | awk '{print "  "$6"  "$5"  "$7}'
python3 -c "
import json;m=json.load(open('/data/fagui_rag/index/meta.json'))
print('  built_at   ', m.get('built_at'))
print('  chunks     ', m.get('chunks_total'))
print('  source_index', m.get('source_index'))
print('  其余字段   ', {k:v for k,v in m.items() if k not in ('note_sources',)} if len(str(m))<2000 else {k:(v if not isinstance(v,list) else ('<%d 项>'%len(v))) for k,v in m.items() if k!='note_sources'})
"
echo
echo "=== 索引目录里各版本的块数 ==="
for d in /data/fagui_rag/index /data/fagui_rag/index_v2 /data/fagui_rag/index_v3; do
  [ -f "$d/chunks.jsonl" ] && printf "  %-34s %s 块  %.1fG\n" "$d" "$(wc -l < $d/chunks.jsonl)" "$(du -s --block-size=1G $d | cut -f1)"
done
echo
echo "=== 8000 端口是什么模型 ==="
curl -s -m 5 http://127.0.0.1:8000/v1/models 2>/dev/null | head -c 300; echo
echo
echo "=== GPU 空闲显存（.10）==="
nvidia-smi --query-gpu=index,memory.used,memory.total,utilization.gpu --format=csv,noheader | \
  awk -F', ' '{printf "  GPU%s 用 %s / %s  利用率 %s\n",$1,$2,$3,$4}'
