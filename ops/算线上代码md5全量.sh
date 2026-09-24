#!/bin/bash
# 把要入库的**整棵目录**逐文件算 md5（比清单口径更全：目录内部的每个文件都算）。
set -u
OUT=/home/test/_导出代码/线上md5_全量.txt
: > "$OUT"
n=0
hash_tree() {   # $1 = 绝对路径或文件
  if [ -f "$1" ]; then
    printf '%s  %s\n' "$(md5sum "$1" | cut -d' ' -f1)" "${1#/}" >> "$OUT"; n=$((n+1))
  elif [ -d "$1" ]; then
    while IFS= read -r f; do
      case "$f" in
        *__pycache__*|*.pyc|*/index/*|*/index.bak*|*okf_bundles*|*/eia_reports_raw/*|*/guides_pdf/*|\
        *_cache*|*_审核结果*|*_生成结果*|*.bak_before_*|*.bak_p[0-9]_*|*.log|*.pid|*.tar.gz) continue ;;
      esac
      printf '%s  %s\n' "$(md5sum "$f" | cut -d' ' -f1)" "${f#/}" >> "$OUT"; n=$((n+1))
    done < <(find "$1" -type f)
  fi
}
hash_tree /home/test/xishu_qingyu_serve/frontend
hash_tree /home/test/xishu_qingyu_serve/xishu_pipeline
hash_tree /home/test/xishu_qingyu_serve/tests
hash_tree /home/test/xishu_qingyu_serve/kg_data
hash_tree /home/test/fagui_serve/fagui_rag_proxy.py
hash_tree /data/eia_audit/audit
hash_tree /data/eia_report_gen/gen
hash_tree /data/eia_report_gen/单测
hash_tree /data/eia_report_gen/样例
hash_tree /data/eia_report_gen/判据库
hash_tree /data/fagui_rag/criteria
hash_tree /data/fagui_rag/retriever.py
hash_tree /data/fagui_rag/ingest_okf.py
echo "全量算得 $n 个文件 → $OUT"
