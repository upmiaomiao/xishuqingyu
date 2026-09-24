#!/bin/bash
# 单文件补丁部署：decide.py（在 A 档四件基础上，再补两处"静默丢数据"）
#   ① 年用量是**字符串**（页面自带样例就是 "3000"）时，原先整体跳过 → 现在按数字解析；
# 用法：bash /home/test/部署decide补丁.sh
set -u
SRC=/home/test/_A档_待部署/decide.py
DST=/data/eia_report_gen/gen/decide.py
TS=$(date +%Y%m%d_%H%M%S)
EXPECT=f3b9b601a42749685c4d561a38aa2c7b      # A 档那版（改前）

echo "==== 1) 改前核对 ===="
LIVE=$(md5sum "$DST" | cut -d' ' -f1)
echo "  线上 md5=$LIVE  期望=$EXPECT"
[ "$LIVE" = "$EXPECT" ] || { echo "  ❌ 不一致，先别部署"; exit 3; }

echo "==== 2) 备份 + 覆盖 ===="
cp -p "$DST" "$DST.bak_before_strnum_$TS"
echo "  备份 → $DST.bak_before_strnum_$TS"
cp -p "$SRC" "$DST"
if python3 -c "import ast,io,sys;ast.parse(io.open(sys.argv[1],encoding='utf-8').read())" "$DST"; then
  echo "  ✅ 部署完成  md5=$(md5sum "$DST" | cut -d' ' -f1)"
else
  echo "  ❌ 语法错误，回滚"; cp -p "$DST.bak_before_strnum_$TS" "$DST"; exit 7
fi
find /data/eia_report_gen/gen/__pycache__ -name 'decide.*.pyc' -delete 2>/dev/null
echo "==== 3) 回滚 ===="
echo "  cp -p $DST.bak_before_strnum_$TS $DST && bash /home/test/安全重启8011.sh"
