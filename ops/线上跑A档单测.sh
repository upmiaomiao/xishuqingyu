#!/bin/bash
# 线上跑 A 档单测：用**服务器上的真实判据目录与引擎路径**跑，确认部署后行为正确。
export EIA_CRITERIA_DIR=/data/fagui_rag/criteria
export PYTHONPATH=/data/eia_audit:/data/eia_report_gen
export AUDIT_HOME=/data/eia_audit
cd /home/test/A档单测 || exit 1
echo "判据目录：$EIA_CRITERIA_DIR"
ls -l /data/fagui_rag/criteria/标准现行性.json
for f in 单测_判据层.py 单测_标准现行性.py 单测_单位折算与措施闸门.py; do
  echo
  echo "================ $f"
  python3 "$f" 2>&1 | tail -6
done
