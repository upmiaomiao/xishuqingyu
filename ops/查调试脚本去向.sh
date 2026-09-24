#!/bin/bash
echo "=== 1. 归档区里找「查模块挂载」==="
find /home/test/_重构归档_20260918 -name '*查模块挂载*' 2>/dev/null | sed 's/^/  /'
echo "  （以上为空表示归档区里没有）"

echo
echo "=== 2. 归档区目录树（前两层）==="
find /home/test/_重构归档_20260918 -maxdepth 2 2>/dev/null | sort | sed 's#/home/test/_重构归档_20260918#  .#'

echo
echo "=== 3. 旧备份文件/ 内容 ==="
if [ -d /home/test/_重构归档_20260918/旧备份文件 ]; then
  ls -l /home/test/_重构归档_20260918/旧备份文件/ | tail -n +2 | awk '{printf "  %8s  %s\n", $5, $9}'
else
  echo "  （目录不存在）"
fi

echo
echo "=== 4. 全盘搜（/home/test 下，含压缩包内）==="
find /home/test -name '*查模块挂载*' 2>/dev/null | sed 's/^/  /'
echo "  -- 压缩包里 --"
for t in $(find /home/test/_重构归档_20260918 -name '*.tar.gz' 2>/dev/null); do
  echo "  [$t]"
  tar tzf "$t" 2>/dev/null | grep '查模块挂载' | sed 's/^/    /'
done

echo
echo "=== 5. 基线里这个文件当时在哪 ==="
grep '查模块挂载' /home/test/_重构归档_20260918/基线md5_20260918-095425.txt | sed 's/^/  /'

echo
echo "=== 6. 线上 static/ 现在有哪些 .js ==="
ls -l /home/test/xishu_qingyu_serve/xishu_pipeline/static/*.js 2>/dev/null | awk '{printf "  %8s  %s\n", $5, $9}'

echo
echo "=== 7. 重构前快照压缩包里有没有它 ==="
SNAP=$(find /home/test/_重构归档_20260918 -name '重构前快照_*.tar.gz' | head -1)
echo "  快照：$SNAP"
tar tzf "$SNAP" 2>/dev/null | grep -i 'static/' | sed 's/^/    /' | head -20
