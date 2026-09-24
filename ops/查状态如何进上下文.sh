#!/usr/bin/env bash
# 只读：status 从索引到"模型看得见的上下文"这条路上，到底在哪几处出现。
set -u
S=/home/test/xishu_qingyu_serve
echo "===== 1) retriever.py 里与 status/废止 有关的行 ====="
grep -n "status\|废止\|ABOLISH" "$S/rag/retriever.py" | head -30

echo
echo "===== 2) 拼给模型的上下文里带不带状态（找 context/prompt 组装处）====="
grep -rn "已废止\|现行" "$S/rag/retriever.py" "$S/xishu_pipeline/"*.py 2>/dev/null | grep -v "^.*#" | head -20

echo
echo "===== 3) is_abolished / 降权 的实现 ====="
sed -n '88,100p' "$S/rag/retriever.py"
echo "  ---- 158-170 ----"
sed -n '158,170p' "$S/rag/retriever.py"
