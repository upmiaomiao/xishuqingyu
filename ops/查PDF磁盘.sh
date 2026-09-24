#!/bin/bash
# 查「找不到原文 PDF」到底是文件不在，还是名字对不上。
echo "=== 1. 服务端 /doc 的换算规则 ==="
grep -n -B 3 -A 22 'def .*doc\|/doc' /home/test/xishu_qingyu_serve/xishu_pipeline/routes.py | head -50

echo
echo "=== 2. PDF 根目录 ==="
echo "  配置的 pdf_root:"
curl -s -m 5 http://127.0.0.1:8011/health | tr ',' '\n' | grep -i pdf

for ROOT in /data/fagui_pdf; do
  if [ -d "$ROOT" ]; then
    echo "  $ROOT 存在，顶层："
    ls "$ROOT" | head -15
    echo "  总 PDF 数：$(find "$ROOT" -name '*.pdf' | wc -l)"
    echo "  「环评报告」子目录里的 PDF 数：$(find "$ROOT/环评报告" -name '*.pdf' 2>/dev/null | wc -l)"
  else
    echo "  ★ $ROOT 不存在"
  fi
done

echo
echo "=== 3. 目标文件到底在不在（各种可能的名字）==="
KEY="苏州"
for ROOT in /data/fagui_pdf; do
  [ -d "$ROOT" ] || continue
  echo "  含「$KEY」且以 .pdf 结尾的文件："
  find "$ROOT" -iname "*${KEY}*.pdf" 2>/dev/null | head -20
  echo
  echo "  含「$KEY」的**所有**文件（不限后缀）："
  find "$ROOT" -iname "*${KEY}*" -type f 2>/dev/null | head -20
done

echo
echo "=== 4. 索引 .md 在哪里、有多少 ==="
for D in /data/fagui_pdf /data/fagui_md /data/fagui_index; do
  [ -d "$D" ] && echo "  $D: md=$(find "$D" -name '*.md' 2>/dev/null | wc -l)  pdf=$(find "$D" -name '*.pdf' 2>/dev/null | wc -l)"
done

echo
echo "=== 5. 直接找那条 .md ==="
find /data -name '*物资再生*' 2>/dev/null | head -20

echo
echo "=== 6. 「环评报告」目录内容抽样 ==="
for ROOT in /data/fagui_pdf; do
  [ -d "$ROOT/环评报告" ] && { echo "  $ROOT/环评报告 前 25 个条目："; ls "$ROOT/环评报告" | head -25; }
done
