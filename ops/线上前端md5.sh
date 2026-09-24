#!/bin/bash
# 核对「工作副本」与「线上」的每一个文件是否一致。
# 动机：2026-09-18 我读工作副本的 index.html 判断"前端还是一行单体"，
# 结论完全错了 —— 线上早就是 22 行的模块化版。工作副本的 index.html 从没同步过，
# 因为之前几轮只往上推 js/*.js，没推 index.html。
# 这个脚本就是为了让"副本过期"这件事下次能一眼看出来。
D=/home/test/xishu_qingyu_serve/frontend
echo "=============== 线上各文件 md5 ==============="
cd "$D" || exit 1
for f in index.html app.css gen.html audit.html js/util.js js/views.js js/message.js \
         js/image.js js/store.js js/kg.js js/ask.js js/main.js; do
  if [ -f "$f" ]; then
    printf '%-18s %8d B  %s\n' "$f" "$(stat -c%s "$f")" "$(md5sum "$f" | cut -d' ' -f1)"
  else
    printf '%-18s （线上没有）\n' "$f"
  fi
done
