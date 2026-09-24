#!/bin/bash
# 只读侦察
set -u
cd /data/fagui_rag || exit 1
echo "===== HJ 1408 在索引里的模样 ====="
python3 /home/test/侦察行业与图谱.py
echo
echo "===== retrieve.py (站点) ====="
md5sum /home/test/xishu_qingyu_serve/xishu_pipeline/retrieve.py
sed -n '1,90p' /home/test/xishu_qingyu_serve/xishu_pipeline/retrieve.py
