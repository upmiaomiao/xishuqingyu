#!/usr/bin/env bash
# 查清站点目录的构成：为什么 find 出来 4.5 万个文件
cd /home/test/xishu_qingyu_serve || exit 1
echo "--- 顶层 ---"
ls -la | head -22
echo "--- 各顶层目录文件数 ---"
for d in */ ; do
  n=$(find "$d" -type f 2>/dev/null | wc -l)
  printf '%-30s %s\n' "$d" "$n"
done | sort -k2 -nr | head -14
echo "--- 代码类文件数（排除 venv/pycache）---"
find . -type f \( -name '*.py' -o -name '*.js' -o -name '*.html' -o -name '*.css' -o -name '*.sh' -o -name '*.json' -o -name '*.md' \) \
  -not -path '*/__pycache__/*' -not -path './.venv/*' | wc -l
echo "--- 这 4.5 万都在哪（按扩展名）---"
find . -type f -not -path './.venv/*' | sed 's/.*\.//' | sort | uniq -c | sort -nr | head -10
echo "--- /home/test 顶层脚本数 ---"
ls /home/test/*.py 2>/dev/null | wc -l
ls /home/test/*.sh 2>/dev/null | wc -l
echo "--- /data/fagui_rag 目录 ---"
du -sh /data/fagui_rag/* 2>/dev/null | sort -h | tail -12
