#!/bin/bash
# 只读核验：用户那 5 个知识问答错例，到底是"语料没入库"还是"入库了但检索/状态有问题"。
# 全部只读（grep/ls），不写任何文件、不重启。
IDX=/data/fagui_rag/index
CH=$IDX/chunks.jsonl
echo "=== 索引文件 ==="
ls -la "$CH" "$IDX/vectors.npy" 2>/dev/null | awk '{print $5, $9}'
echo
echo "=== 1) 生态环境法典 在索引里吗 ==="
grep -c "中华人民共和国生态环境法典" "$CH" 2>/dev/null || echo 0
echo "   法典块里有没有那一句（第一千二百四十二条 / 同时废止）:"
grep -c "第一千二百四十二条" "$CH" 2>/dev/null || echo 0
grep -o "2026年8月15日" "$CH" 2>/dev/null | wc -l
echo
echo "=== 2) 固废法/环评法 在索引里的 status ==="
for k in "固体废物污染环境防治法" "环境影响评价法"; do
  n=$(grep -c "$k" "$CH" 2>/dev/null || echo 0)
  echo "  $k：$n 块"
done
echo "  索引里 status 字段的取值分布（前 8）:"
grep -o '"status": *"[^"]*"' "$CH" 2>/dev/null | sort | uniq -c | sort -rn | head -8
echo "  已废止/已失效 标记的块数:"
grep -c '"status": *"\(已废止\|废止\|已失效\|已作废\)"' "$CH" 2>/dev/null || echo 0
echo
echo "=== 3) GB3095-2026 / GB3095-2012 ==="
for k in "GB 3095—2026" "GB 3095-2026" "GB3095-2026" "GB 3095—2012" "GB 3095-2012" "3095—2026"; do
  printf "  %-16s %s 块\n" "$k" "$(grep -c "$k" "$CH" 2>/dev/null || echo 0)"
done
echo "  2026 版特有的过渡期措辞在不在（过渡阶段/2030年12月31日）:"
grep -c "过渡阶段" "$CH" 2>/dev/null || echo 0
grep -c "2030年12月31日" "$CH" 2>/dev/null || echo 0
echo
echo "=== 4) GB8978 第一类污染物 ==="
for k in "污水综合排放标准" "第一类污染物" "车间或车间处理设施排放口" "总汞"; do
  printf "  %-22s %s 块\n" "$k" "$(grep -c "$k" "$CH" 2>/dev/null || echo 0)"
done
echo
echo "=== 5) 江苏太湖地方标准 DB32/1072 ==="
for k in "DB32" "1072" "太湖" "DB33"; do
  printf "  %-8s %s 块\n" "$k" "$(grep -c "$k" "$CH" 2>/dev/null || echo 0)"
done
echo
echo "=== 6) 语料树里这些文件在不在（okf_bundles）==="
for p in "生态环境法律法规/法律" "生态环境标准规范/大气环境保护" "生态环境标准规范/水环境保护"; do
  d="/data/fagui_rag/okf_bundles/$p"
  echo "  $d: $(ls "$d" 2>/dev/null | wc -l) 个子项"
done
find /data/fagui_rag/okf_bundles -name "*生态环境法典*" -o -name "*3095*" -o -name "*8978*" 2>/dev/null | head -12
echo
echo "=== 7) FAQ 缓存（复测前必须知道，否则会把缓存命中当成没修好）==="
curl -s --max-time 8 http://127.0.0.1:8011/audit/api/../cache/stats 2>/dev/null | head -c 300
curl -s --max-time 8 http://127.0.0.1:8011/cache/stats 2>/dev/null | head -c 300
echo
echo "=== 8) 索引总量 ==="
wc -l < "$CH"
