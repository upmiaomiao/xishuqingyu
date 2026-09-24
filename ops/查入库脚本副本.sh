#!/usr/bin/env bash
# 找服务器上所有 ingest / 回填 脚本副本，并比对特征
echo "=== /data/fagui_rag 下的 py ==="
ls -la /data/fagui_rag/*.py 2>/dev/null
echo
echo "=== /home/test 下名字含 ingest/回填/表格 的脚本 ==="
ls -la /home/test/*ingest* /home/test/*回填* /home/test/*表格* 2>/dev/null
echo
echo "=== 各副本是否含『表格单独成块』与『来源抬头』特征 ==="
for f in /data/fagui_rag/ingest_okf.py /data/fagui_rag/ingest_okf*.py /home/test/ingest_okf*.py; do
  [ -f "$f" ] || continue
  tbl=$(grep -c "_is_table" "$f" 2>/dev/null)
  hdr=$(grep -c "来源抬头\|【{" "$f" 2>/dev/null)
  lines=$(wc -l < "$f")
  md5=$(md5sum "$f" | cut -c1-12)
  printf '%-52s 行 %-5s md5 %s  表格切块:%s  抬头:%s\n' "$f" "$lines" "$md5" "$tbl" "$hdr"
done
echo
echo "=== 回填脚本与它的产物 ==="
ls -la /data/fagui_rag/ | grep -iE "stage|回填|bak"
echo
echo "=== okf_bundles 与 okf_bundles_stage 的规模 ==="
for d in /data/fagui_rag/okf_bundles /data/fagui_rag/okf_bundles_stage; do
  printf '%-42s md %s 份  %s\n' "$d" "$(find "$d" -name '*.md' | wc -l)" "$(du -sh "$d" | cut -f1)"
done
