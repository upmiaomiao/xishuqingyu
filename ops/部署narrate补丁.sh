#!/bin/bash
# 单文件补丁部署：narrate.py（C9-① 判定改为看「措施内容」有没有字，而不是字段在不在）
# 实测依据：`环保措施` 是必填项 —— 用户不可能整个字段不填（接口判 rejected），
#          真正会发生的是"字段在、里面空着"。原判定看事实表前缀，空行也会被判成"有措施"。
# 用法：bash /home/test/部署narrate补丁.sh
set -u
SRC=/home/test/_A档_待部署/narrate.py
DST=/data/eia_report_gen/gen/narrate.py
TS=$(date +%Y%m%d_%H%M%S)
EXPECT=7c86ad2bae7129fda44464267fdcd9bf      # A 档那版（改前）

echo "==== 1) 改前核对 ===="
LIVE=$(md5sum "$DST" | cut -d' ' -f1)
echo "  线上 md5=$LIVE  期望=$EXPECT"
[ "$LIVE" = "$EXPECT" ] || { echo "  ❌ 不一致，先别部署"; exit 3; }

echo "==== 2) 备份 + 覆盖 ===="
cp -p "$DST" "$DST.bak_before_hasmeasure_$TS"
echo "  备份 → $DST.bak_before_hasmeasure_$TS"
cp -p "$SRC" "$DST"
if python3 -c "import ast,io,sys;ast.parse(io.open(sys.argv[1],encoding='utf-8').read())" "$DST"; then
  echo "  ✅ 部署完成  md5=$(md5sum "$DST" | cut -d' ' -f1)"
else
  echo "  ❌ 语法错误，回滚"; cp -p "$DST.bak_before_hasmeasure_$TS" "$DST"; exit 7
fi
find /data/eia_report_gen/gen/__pycache__ -name 'narrate.*.pyc' -delete 2>/dev/null
echo "==== 3) 回滚 ===="
echo "  cp -p $DST.bak_before_hasmeasure_$TS $DST && bash /home/test/安全重启8011.sh"
