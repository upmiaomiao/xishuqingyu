#!/bin/bash
# 我们项目的占用与运行状态（.10）
echo "=== /data/fagui_rag 各目录 ==="
du -sh /data/fagui_rag 2>/dev/null | sed 's/^/  合计  /'
du -sh /data/fagui_rag/* 2>/dev/null | sort -rh | head -12 | sed 's/^/  /'
echo
echo "=== 索引 === "
for d in /data/fagui_rag/index /data/fagui_rag/index_v2 /data/fagui_rag/index_v3* /data/fagui_rag/index.bak*; do
  [ -e "$d" ] && printf "  %-52s %s\n" "$d" "$(du -sh $d 2>/dev/null | cut -f1)"
done
echo
echo "=== 线上索引块数 / 向量维度 ==="
python3 - <<'PY' 2>/dev/null || echo "  （读取失败）"
import json
try:
    m = json.load(open('/data/fagui_rag/index/meta.json'))
    print("  meta:", {k: m[k] for k in list(m)[:8]})
except Exception as e:
    print("  meta.json:", e)
PY
wc -l /data/fagui_rag/index/chunks.jsonl 2>/dev/null | awk '{printf "  chunks.jsonl %s 行\n",$1}'
ls -la /data/fagui_rag/index/*.npy 2>/dev/null | awk '{printf "  %s  %.2f GB\n",$9,$5/1073741824}'
echo
echo "=== 站点进程 ==="
ps -eo pid,ppid,rss,etime,pcpu,pmem,args 2>/dev/null | grep -E 'xishu|8011' | grep -v grep | \
  awk '{printf "  pid=%s 内存=%.1fG 已运行=%s cpu=%s%% mem=%s%%\n",$1,$3/1048576,$4,$5,$6}'
echo
echo "=== 站点日志大小 ==="
ls -la --time-style=+%F /home/test/xishu_qingyu_serve/*.log 2>/dev/null | awk '{printf "  %s  %.1f MB  改于 %s\n",$7,$5/1048576,$6}'
echo
echo "=== 近 200 行日志里的错误 ==="
tail -400 /home/test/xishu_qingyu_serve/qa_8011.log 2>/dev/null | grep -iE 'error|traceback|exception|失败' | tail -5 | sed 's/^/  /'
echo
echo "=== 备份目录 ==="
ls -d /data/fagui_rag/_backup* /data/fagui_rag/index.bak* /data/fagui_rag/*.bak* 2>/dev/null | while read d; do
  printf "  %-58s %s\n" "$d" "$(du -sh $d 2>/dev/null | cut -f1)"
done
