#!/bin/bash
# 修正阶段 1 的备份：从阶段 0 快照里取回真正的原版，并核对一切
D=/home/test/xishu_qingyu_serve
P=$D/xishu_pipeline
ARC=/home/test/_重构归档_20260918
SNAP=$(ls -t $ARC/重构前快照_*.tar.gz | head -1)

echo "=========== 1. 线上 routes.py 到底是什么版本 ==========="
echo "  当前线上：$(stat -c%s "$P/routes.py") 字节  md5 $(md5sum "$P/routes.py" | cut -d' ' -f1)"
echo "  （我本地改后是 8326 字节）"

echo
echo "=========== 2. 从阶段 0 快照取回真正的原版 ==========="
echo "  快照：$(basename "$SNAP")  建于 $(stat -c%y "$SNAP" | cut -d. -f1)"
mkdir -p "$ARC/阶段1前"
tar xzf "$SNAP" -C "$ARC/阶段1前" --strip-components=1 xishu_pipeline/routes.py 2>/dev/null \
  || tar xzf "$SNAP" -C "$ARC/阶段1前" xishu_pipeline/routes.py
ORIG=$(find "$ARC/阶段1前" -name routes.py | head -1)
echo "  取回：$ORIG"
echo "  大小：$(stat -c%s "$ORIG") 字节  md5 $(md5sum "$ORIG" | cut -d' ' -f1)"

echo
echo "=========== 3. 与阶段 0 记录的基线 md5 核对 ==========="
BASE=$(ls -t $ARC/基线md5_*.txt | head -1)
echo "  基线文件：$(basename "$BASE")"
grep 'xishu_pipeline/routes.py' "$BASE" | sed 's/^/  基线记录：/'
echo "  取回文件：$(md5sum "$ORIG" | cut -d' ' -f1)  xishu_pipeline/routes.py"
if [ "$(md5sum "$ORIG" | cut -d' ' -f1)" = "$(grep 'xishu_pipeline/routes.py' "$BASE" | cut -d' ' -f1)" ]; then
  echo "  ★ 一致 —— 这才是改动前的真原版"
  cp -p "$ORIG" "$ARC/阶段1前/routes.py.原版"
  echo "  已存为 $ARC/阶段1前/routes.py.原版"
else
  echo "  ✗ 不一致，需要进一步查"
fi

echo
echo "=========== 4. 删掉那个假的备份 ==========="
# 那个 f36a3b0d... 的 routes.py 是覆盖后的副本，留着会误导
if [ "$(md5sum "$ARC/阶段1前/routes.py" | cut -d' ' -f1)" = "$(md5sum "$P/routes.py" | cut -d' ' -f1)" ]; then
  rm -f "$ARC/阶段1前/routes.py"
  echo "  已删除误标为「备份」的覆盖后副本"
fi
ls -1 "$ARC/阶段1前/"

echo
echo "=========== 5. 阶段 1 功能其实是对的（复核一遍）==========="
echo "  /static/app.css（文件不存在，应 404 缺失）: $(curl -s -m 10 http://127.0.0.1:8011/static/app.css)"
echo "  /static/nope.css（白名单外，应 404 不存在）: $(curl -s -m 10 http://127.0.0.1:8011/static/nope.css)"
echo "  / 首页：$(curl -s -o /dev/null -w '%{http_code}' -m 20 http://127.0.0.1:8011/)  $(curl -s -m 20 http://127.0.0.1:8011/ | wc -c) 字节"

echo
echo "=========== 6. 生成目录为什么是 47 不是 46 ==========="
OUT=/data/eia_report_gen/_生成结果
echo "  顶层 .docx：$(ls $OUT/*.docx 2>/dev/null | wc -l)"
echo "  最新的 3 份："
ls -lt --time-style=+%m-%d\ %H:%M "$OUT"/*.docx | head -3 | sed 's#.*_生成结果/##' | sed 's/^/    /'
echo "  带 20260918 的：$(ls $OUT/*20260918*.docx 2>/dev/null | wc -l)"
