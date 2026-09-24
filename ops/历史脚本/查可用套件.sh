#!/bin/bash
echo "=== 1. 站点目录下的检查脚本 ==="
ls -la /home/test/xishu_qingyu_serve/*.py 2>/dev/null

echo
echo "=== 2. tools / tests 目录 ==="
ls -d /home/test/xishu_qingyu_serve/*/ 2>/dev/null
for d in tools tests scripts check; do
  ls /home/test/xishu_qingyu_serve/$d 2>/dev/null && echo "  ^-- $d/"
done

echo
echo "=== 3. 全盘找 check_* / 契约 / 冒烟 脚本 ==="
find /home/test -maxdepth 3 -name 'check_*.py' 2>/dev/null | head -30
find /home/test -maxdepth 3 -name '*契约*.py' 2>/dev/null | head -20
find /home/test -maxdepth 3 -name '*冒烟*' 2>/dev/null | head -10

echo
echo "=== 4. xishu_pipeline 下的模块 ==="
ls -la /home/test/xishu_qingyu_serve/xishu_pipeline/*.py | head -40
