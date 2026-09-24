#!/bin/bash
# 确认：环评报告只有 .md（提取全文）、没有 .pdf。
# 若 .md 内容完整，"查看原文"完全可以退化成**文本版预览**，而不是报"找不到"。
echo "=== 1. 服务器有没有解压/工具 ==="
for t in unrar unar 7z 7za bsdtar rar; do
  if command -v "$t" >/dev/null 2>&1; then echo "  OK  $t -> $(command -v $t)"; else echo "  --  $t"; fi
done

echo
echo "=== 2. 磁盘 ==="
df -h /data | tail -1

echo
echo "=== 3. 那条环评报告的 .md 是否存在、多大、内容如何 ==="
MD="/data/fagui_rag/okf_bundles/环评报告/中华人民共和国生态环境部 - 2023 - 江苏苏州市物资再生有限公司报废机动车机械化拆解项目环境影响报告.md"
if [ -f "$MD" ]; then
  echo "  √ 存在，大小：$(du -h "$MD" | cut -f1)  行数：$(wc -l < "$MD")"
  echo "  --- 前 25 行 ---"
  head -25 "$MD"
  echo "  --- 后 7 行 ---"
  tail -7 "$MD"
else
  echo "  × 不存在：$MD"
fi

echo
echo "=== 4. okf_bundles/环评报告 的整体情况 ==="
D=/data/fagui_rag/okf_bundles/环评报告
echo "  .md 数量：$(find "$D" -name '*.md' | wc -l)"
echo "  总体积：$(du -sh "$D" | cut -f1)"
echo "  最大的 5 个："
find "$D" -name '*.md' -printf '%s %p\n' 2>/dev/null | sort -rn | head -5 | while read sz p; do
  printf "    %6.1f KB  %s\n" "$(echo "$sz/1024" | bc -l)" "$(basename "$p")"
done
echo "  最小的 3 个："
find "$D" -name '*.md' -printf '%s %p\n' 2>/dev/null | sort -n | head -3 | while read sz p; do
  printf "    %6d B   %s\n" "$sz" "$(basename "$p")"
done

echo
echo "=== 5. 索引里 source 是怎么写的（前端拼 /doc 用的就是它）==="
echo "  服务器上 okf_bundles 下就是 .md 的相对路径，例如："
ls "$D" | head -4

echo
echo "=== 6. 有没有别的目录其实存着这些 PDF ==="
echo "  /data 下所有目录名含 环评 的："
find /data -maxdepth 3 -type d -iname '*环评*' 2>/dev/null | head -12
