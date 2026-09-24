#!/bin/bash
# C5 名录匹配修复上线：替换 /data/eia_audit/audit/criteria.py（审核线与生成线共用这一份）。
# 纪律：先核对线上版本 == 我改前的版本，再备份、再替换、再自检；判据库一个字不动。
set -u
TS=$(date +%Y%m%d_%H%M%S)
DST=/data/eia_audit/audit/criteria.py
NEW=/tmp/criteria.py.c5fix
BAK=$DST.bak_before_c5code_$TS
WANT_BEFORE=2b554a0c1a24dba4f73f025c76cf4335     # 我改前那份的 md5（本地/线上都是它）

echo "==== 1) 部署前核对 ===="
echo "  线上 md5 : $(md5sum "$DST" | cut -d' ' -f1)"
echo "  期望(改前): $WANT_BEFORE"
echo "  待装 md5 : $(md5sum "$NEW" | cut -d' ' -f1)"
if [ "$(md5sum "$DST" | cut -d' ' -f1)" != "$WANT_BEFORE" ]; then
  echo "❌ 线上版本与预期不符（可能已被别人改过）—— 停止部署，先人工核对"
  exit 1
fi
python3 -c "import py_compile;py_compile.compile('$NEW',doraise=True);print('  语法检查 ✅')" || exit 1

echo
echo "==== 2) 备份 ===="
cp -p "$DST" "$BAK"
echo "  备份 → $BAK"
echo "  备份 md5: $(md5sum "$BAK" | cut -d' ' -f1)"

echo
echo "==== 3) 替换 ===="
cp -p "$NEW" "$DST"
chmod --reference="$BAK" "$DST" 2>/dev/null
chown --reference="$BAK" "$DST" 2>/dev/null
echo "  现线上 md5: $(md5sum "$DST" | cut -d' ' -f1)"

echo
echo "==== 4) 三个新函数在位 ===="
grep -n -e 'def industry_codes' -e 'def code_in_query' -e 'def lead_name_tokens' "$DST"

echo
echo "==== 5) 清 pyc 缓存（避免旧字节码被复用）===="
rm -f /data/eia_audit/audit/__pycache__/criteria.*.pyc
ls /data/eia_audit/audit/__pycache__/ 2>/dev/null | grep -c criteria || true

echo
echo "==== 6) 判据库未被动过（只读校验：列出即可）===="
ls -l /data/eia_report_gen/判据库/分类管理名录2021.json
