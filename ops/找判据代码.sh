#!/bin/bash
# 定位"判据代码"在服务器上的真实副本（审核线与生成线共用 criteria.py）。
# 只读，不改任何东西。
echo "==== 1) criteria.py 的所有副本 ===="
for f in $(find / -name 'criteria.py' -not -path '*/node_modules/*' -not -path '/proc/*' 2>/dev/null); do
  md5sum "$f"
  stat -c '     %y  %s 字节' "$f"
done

echo
echo "==== 2) 判据库位置 ===="
ls -d /data/eia_report_gen/判据库 2>/dev/null
ls -d /data/*/判据库 2>/dev/null
ls -d /home/test/*/判据库 2>/dev/null

echo
echo "==== 3) 8011 进程环境变量（判据库/审核相关）===="
pid=$(pgrep -f xishu_qingyu_qa.py | head -1)
echo "pid=$pid"
if [ -n "$pid" ]; then
  tr '\0' '\n' < /proc/$pid/environ 2>/dev/null | grep -i -e CRITERIA -e AUDIT -e EIA_ | head -12
fi

echo
echo "==== 4) 生成线代码（decide.py / gen）在哪 ===="
find / -name 'decide.py' -not -path '*/node_modules/*' 2>/dev/null | head -5

echo
echo "==== 5) 单测目录（服务器上有没有单测可跑）===="
ls -d /data/eia_audit 2>/dev/null && ls /data/eia_audit | head -20
ls /home/test/xishu_qingyu_serve | head -20
