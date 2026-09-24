#!/bin/bash
F=/home/test/xishu_qingyu_serve/frontend/index.html
echo "=== 前端文件 ==="
ls -l $F
echo
echo "=== 入口关键词计数 ==="
for k in 报告编制 报告生成 智能审核 知识图谱 专业研判 现场照片; do
  printf "%-10s %s\n" "$k" "$(grep -o "$k" $F | wc -l)"
done
echo
echo "=== 侧边栏/导航条目 ==="
grep -oE 'data-view="[a-zA-Z_]+"' $F | sort | uniq -c
echo
echo "=== /gen 页面可访问性 ==="
for p in /gen /gen/ /gen/api/outputs /audit /audit/; do
  printf "%-20s -> %s\n" "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 10 http://127.0.0.1:8011$p)"
done
echo
echo "=== 生成侧真实跑一次（自测生成页）==="
ls -l /home/test/xishu_qingyu_serve/*自测* 2>/dev/null
ls -l /home/test/xishu_qingyu_serve/tools/*自测* 2>/dev/null
find /home/test/xishu_qingyu_serve -maxdepth 3 -name '*自测生成页*' 2>/dev/null
