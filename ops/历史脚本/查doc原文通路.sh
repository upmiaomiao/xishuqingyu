#!/bin/bash
echo "=== 1. /doc 的实现（找 PDF 的那段）==="
grep -rn "未找到原文 PDF\|pdf_root\|PDF_ROOT\|def api_doc\|/doc" /home/test/xishu_qingyu_serve/xishu_pipeline/*.py | head -30

echo
echo "=== 2. /data/fagui_pdf 结构（顶层）==="
ls /data/fagui_pdf | head -20
echo "--- 顶层条目数 ---"
ls /data/fagui_pdf | wc -l
echo "--- 环评报告 子目录是否存在 ---"
ls -d /data/fagui_pdf/环评报告 2>/dev/null && ls /data/fagui_pdf/环评报告 | wc -l || echo "  不存在 /data/fagui_pdf/环评报告"

echo
echo "=== 3. 那几个 404 的来源，PDF 到底在不在 ==="
for f in "环评报告/米东固废综合处理厂及配套设施项目-生活垃圾焚烧发电工程环境影响报告书" "环评报告/环评气化80t 宜川县" "环评报告/原油管道项目环境影响报告书"; do
  echo "[$f]"
  ls -l "/data/fagui_pdf/$f.pdf" 2>/dev/null || echo "    /data/fagui_pdf/$f.pdf 不存在"
done

echo
echo "=== 4. 全库统计：索引 .md 数 vs 有 PDF 的数 ==="
IDX=/data/fagui_rag
ls $IDX | head
echo "--- 索引目录 ---"
ls -d $IDX/* 2>/dev/null | head -20

echo
echo "=== 5. /data/eia_reports 里有什么 ==="
ls /data/eia_reports 2>/dev/null | head -10
ls /data/eia_reports 2>/dev/null | wc -l

echo
echo "=== 6. 全盘找那几个 PDF ==="
find /data -maxdepth 3 -name "*米东固废*" 2>/dev/null | head -5
find /data -maxdepth 3 -name "*宜川县*" 2>/dev/null | head -5

echo
echo "=== 7. fagui_pdf 里到底有哪些顶层目录 ==="
du -sh /data/fagui_pdf/* 2>/dev/null | sort -h | tail -20
