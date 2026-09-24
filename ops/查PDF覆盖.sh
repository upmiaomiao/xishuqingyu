#!/bin/bash
# 量化「查看原文」的失效范围：索引里有多少条 source 根本找不到对应 PDF。
echo "=== 索引 .md 的分布（okf_bundles）==="
for d in /data/fagui_rag/okf_bundles/*/; do
  n=$(find "$d" -name '*.md' 2>/dev/null | wc -l)
  b=$(basename "$d")
  p=$(find "/data/fagui_pdf/$b" -name '*.pdf' 2>/dev/null | wc -l)
  if [ "$n" -gt 0 ]; then
    printf "  %-28s md=%-6s pdf=%-6s\n" "$b" "$n" "$p"
  fi
done

echo
echo "=== 全盘找环评报告的 PDF（可能在别处）==="
echo "  /data 下所有含「拆解」的 pdf："
find /data -iname '*拆解*.pdf' 2>/dev/null | head -10
echo "  /data 下名字含「物资再生」的 pdf："
find /data -iname '*物资再生*.pdf' 2>/dev/null | head -10
echo "  整个 /data 的 pdf 总数：$(find /data -name '*.pdf' 2>/dev/null | wc -l)"
echo "  /home 下的 pdf 总数：$(find /home -name '*.pdf' 2>/dev/null | wc -l)"
echo "  /home 下含「物资再生」的文件："
find /home -iname '*物资再生*' 2>/dev/null | head -10

echo
echo "=== okf_bundles/环评报告 有多少条 ==="
find /data/fagui_rag/okf_bundles/环评报告 -name '*.md' 2>/dev/null | wc -l

echo
echo "=== eia_reports_raw 里有没有原始 PDF ==="
ls /data/fagui_rag/eia_reports_raw/ 2>/dev/null | head -8
echo "  该目录文件总数：$(find /data/fagui_rag/eia_reports_raw -type f 2>/dev/null | wc -l)"
echo "  其中 .pdf：$(find /data/fagui_rag/eia_reports_raw -name '*.pdf' 2>/dev/null | wc -l)"
echo "  其中 .md ：$(find /data/fagui_rag/eia_reports_raw -name '*.md' 2>/dev/null | wc -l)"

echo
echo "=== 索引器是从哪读 PDF 的（找配置）==="
grep -rn 'fagui_pdf\|PDF_ROOT\|okf_bundles\|eia_reports_raw' /home/test/xishu_qingyu_serve/xishu_pipeline/*.py 2>/dev/null | head -12
