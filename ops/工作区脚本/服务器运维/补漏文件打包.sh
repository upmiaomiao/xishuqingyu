#!/bin/bash
# 补漏：把上一版导出漏掉的站点顶层脚本 + 两个体检脚本打包（含逐个 md5，便于落地后核对）。
set -u
OUT=/home/test/_导出代码/补漏代码.tar.gz
cd / || exit 1
FILES=(
  home/test/xishu_qingyu_serve/xishu_qingyu_qa.py
  home/test/xishu_qingyu_serve/嵌入报告编制视图.py
  home/test/xishu_qingyu_serve/挂载生成入口.py
  home/test/xishu_qingyu_serve/查嵌入契约.py
  home/test/xishu_qingyu_serve/查生成界面契约.py
  home/test/xishu_qingyu_serve/查生成速度.py
  home/test/xishu_qingyu_serve/查直排来源.py
  home/test/xishu_qingyu_serve/自测生成页.py
  home/test/体检.sh
  home/test/体检_我们的.sh
  home/test/列服务器代码清单.py
)
tar -czf "$OUT" "${FILES[@]}"
echo "==== 打包 ===="
ls -l "$OUT"
echo "包内 $(tar -tzf "$OUT" | wc -l) 个文件"
echo "==== md5（落地后核对用）===="
for f in "${FILES[@]}"; do md5sum "/$f"; done
