#!/usr/bin/env bash
# 只读：定位 Retriever 类，核实"已废止降权"到底在不在线上生效。
set -u
echo "===== 1) 线上所有 retriever.py ====="
find /home/test /data -name "retriever.py" -not -path "*/_重构归档*" -not -path "*/_归档*" 2>/dev/null | head

echo
echo "===== 2) 逐份看 ABOLISHED / is_abolished ====="
for f in $(find /home/test /data -name "retriever.py" -not -path "*/_重构归档*" -not -path "*/_归档*" 2>/dev/null); do
  n=$(grep -c "ABOLISHED\|is_abolished" "$f" 2>/dev/null || echo 0)
  echo "  [$n 处]  $f"
  grep -n "ABOLISHED_PENALTY\|ABOLISHED_STATUS\|def is_abolished" "$f" 2>/dev/null | head -6
done

echo
echo "===== 3) 站点进程实际 import 的是哪一份（看 sys.path/启动脚本）====="
grep -rn "Retriever\|retriever" /home/test/xishu_qingyu_serve/xishu_pipeline/retrieve.py | head -6
ls -l /home/test/xishu_qingyu_serve/xishu_pipeline/rag/ 2>/dev/null | head
