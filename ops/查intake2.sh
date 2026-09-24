#!/bin/bash
echo "=== sys.path 里怎么找到 gen 的：看服务怎么起的 ==="
sed -n '1,40p' /home/test/launch_xishu_qingyu_qa_8011.sh
echo
echo "=== 全盘找 gen/intake.py（限 /data /home /opt /srv）==="
for r in /data /home /opt /srv; do
  find "$r" -maxdepth 6 -path '*/gen/intake.py' -not -path '*/__pycache__/*' 2>/dev/null
done
echo
echo "=== 找所有 intake.py ==="
for r in /data /home /opt /srv; do
  find "$r" -maxdepth 6 -name 'intake.py' -not -path '*/__pycache__/*' 2>/dev/null
done
