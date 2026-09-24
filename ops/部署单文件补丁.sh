#!/bin/bash
# 通用单文件补丁部署（改前 md5 核对 → 备份 → 覆盖 → 语法校验 → 打印回滚）
# 用法：bash /home/test/部署单文件补丁.sh <暂存目录里的文件名> <目标绝对路径> <改前md5|?> <备份后缀>
#   先把新文件 upload 到 /home/test/_A档_待部署/ 下；改前 md5 传 ? 时只打印线上值，不做改动。
set -u
NAME="${1:?用法: 部署单文件补丁.sh <暂存名> <目标路径> <改前md5|?> <备份后缀>}"
DST="${2:?缺少目标路径}"
EXPECT="${3:-?}"
SUF="${4:-patch}"
SRC="/home/test/_A档_待部署/$NAME"
TS=$(date +%Y%m%d_%H%M%S)

[ -f "$SRC" ] || { echo "❌ 暂存缺文件：$SRC（先 upload）"; exit 2; }
LIVE=$(md5sum "$DST" | cut -d' ' -f1)
NEW=$(md5sum "$SRC" | cut -d' ' -f1)
echo "暂存 $NAME  md5=$NEW"
echo "线上 $DST  md5=$LIVE"
if [ "$EXPECT" = "?" ]; then
  echo "（只查询，未改动。要部署就把 $LIVE 作为第 3 个参数再跑一次）"
  exit 0
fi
[ "$LIVE" = "$EXPECT" ] || { echo "❌ 线上 md5 ≠ 期望（$EXPECT）—— 先别部署，人工看一下"; exit 3; }
[ "$LIVE" != "$NEW" ] || { echo "（线上已是这版，无需部署）"; exit 0; }

cp -p "$DST" "$DST.bak_before_${SUF}_$TS"
echo "备份 → $DST.bak_before_${SUF}_$TS"
cp -p "$SRC" "$DST"
case "$NAME" in
  *.py)
    if python3 -c "import ast,io,sys;ast.parse(io.open(sys.argv[1],encoding='utf-8').read())" "$DST"; then
      echo "✅ 部署完成（语法 OK）  md5=$(md5sum "$DST" | cut -d' ' -f1)"
    else
      echo "❌ 语法错误，回滚"; cp -p "$DST.bak_before_${SUF}_$TS" "$DST"; exit 7
    fi
    ;;
  *.json)
    python3 -m json.tool "$DST" > /dev/null && echo "✅ 部署完成（JSON OK）" || { echo "❌ JSON 非法，回滚"; exit 8; }
    ;;
  *) echo "✅ 部署完成（未做语法校验）" ;;
esac
find "$(dirname "$DST")/__pycache__" -name "$(basename "${DST%.*}").*.pyc" -delete 2>/dev/null
echo "回滚：cp -p $DST.bak_before_${SUF}_$TS $DST && bash /home/test/安全重启8011.sh"
