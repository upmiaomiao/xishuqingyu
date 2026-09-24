#!/usr/bin/env bash
# 看入库脚本到底怎么算向量的（预检发现线上向量与"直接调 34004"对不上，必须查清配方）
cd /data/fagui_rag
ls -la *.py 2>/dev/null
echo "=========== 与嵌入相关的代码 ==========="
grep -n "embed\|vector\|model\|batch\|max_length\|prefix\|instruction\|np.save\|float16\|normalize" ingest_okf.py 2>/dev/null | head -60
