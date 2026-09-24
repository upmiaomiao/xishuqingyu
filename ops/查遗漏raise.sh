#!/bin/bash
# 检查线上包里"不在工作副本中"的那些 .py 有没有 raise HTTPException / 直接返回错误
cd /home/test/xishu_qingyu_serve/xishu_pipeline || exit 1
EXTRA="compose.py __init__.py kg.py postprocess.py prompts.py retrieve.py route.py splitter.py textclean.py understand.py"
echo "===== 这些文件里的 raise / HTTPException ====="
for f in $EXTRA; do
  [ -f "$f" ] || continue
  n=$(grep -c 'HTTPException' "$f" 2>/dev/null || echo 0)
  r=$(grep -c 'raise ' "$f" 2>/dev/null || echo 0)
  printf '  %-18s HTTPException=%s  raise=%s\n' "$f" "$n" "$r"
done
echo
echo "===== 具体行 ====="
grep -n 'HTTPException\|raise ' $EXTRA 2>/dev/null
echo
echo "===== 检查 _JOBS/_SESS 之外还有没有别的模块级可变字典 ====="
grep -n '^_[A-Z_]*: dict\|^_[A-Z_]* = {}' *.py
