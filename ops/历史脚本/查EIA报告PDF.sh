#!/bin/bash
echo "=== 1. okf_bundles/环评报告 里有没有 PDF ==="
ls /data/fagui_rag/okf_bundles/环评报告 | head -10
echo "--- 条目数 ---"
ls /data/fagui_rag/okf_bundles/环评报告 | wc -l
echo "--- 其中 .pdf 数 ---"
ls /data/fagui_rag/okf_bundles/环评报告/*.pdf 2>/dev/null | wc -l
echo "--- 其中 .md 数 ---"
ls /data/fagui_rag/okf_bundles/环评报告/*.md 2>/dev/null | wc -l
echo "--- 类型分布 ---"
ls /data/fagui_rag/okf_bundles/环评报告 | sed 's/.*\.//' | sort | uniq -c

echo
echo "=== 2. 对照：okf_bundles/生态环境标准规范 里有什么 ==="
ls /data/fagui_rag/okf_bundles/生态环境标准规范 | head -5
ls /data/fagui_rag/okf_bundles/生态环境标准规范 | sed 's/.*\.//' | sort | uniq -c

echo
echo "=== 3. fagui_pdf 与 okf_bundles 目录名对照 ==="
echo "--- fagui_pdf ---"
ls /data/fagui_pdf
echo "--- okf_bundles ---"
ls /data/fagui_rag/okf_bundles

echo
echo "=== 4. 全盘找 EIA 报告 PDF（按名字找 3 个已知来源）==="
for n in "米东固废" "宜川县" "原油管道项目环境影响报告书"; do
  echo "[$n]"
  find /data -name "*${n}*.pdf" 2>/dev/null | head -3
  echo "   （以上为空表示全盘无此 PDF）"
done

echo
echo "=== 5. ingest 脚本里 source 前缀怎么定的 ==="
grep -n "okf_bundles\|环评报告\|source\|PDF" /data/fagui_rag/ingest_okf.py | head -30
