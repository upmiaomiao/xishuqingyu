#!/bin/bash
# 查 09:48:28 那份草稿是谁生成的 —— 不许有来历不明的产物
D=/home/test/xishu_qingyu_serve
OUT=/data/eia_report_gen/_生成结果

echo "=========== 1. 那份文件的完整信息 ==========="
F=$(ls -t $OUT/*20260918-094828* 2>/dev/null | head -1)
ls -l --time-style=full-iso "$F" | sed 's/^/  /'
echo "  md5 $(md5sum "$F" | cut -d' ' -f1)"

echo
echo "=========== 2. 站点访问日志里 09:4x 的生成请求 ==========="
echo "  --- 日志文件 ---"
ls -l --time-style=+%m-%d\ %H:%M $D/*.log 2>/dev/null | sed 's/^/  /'
echo
echo "  --- 09:47 ~ 09:50 的 POST /gen/api/run ---"
grep -E '09:4[7-9]|09:50' $D/qa_8011.log 2>/dev/null | grep -E 'gen/api/run|gen/api/chat' | head -20 | sed 's/^/  /'
echo
echo "  --- 09:4x 全部请求（前 30 行）---"
grep -E '09:4[0-9]' $D/qa_8011.log 2>/dev/null | head -30 | sed 's/^/  /'

echo
echo "=========== 3. 有没有后台任务还在跑 ==========="
ps -ef | grep -E '自测生成页|全面测试|python.*gen' | grep -v grep | sed 's/^/  /' || echo "  无"

echo
echo "=========== 4. 归档目录现状 ==========="
for d in "$OUT"/_*; do [ -d "$d" ] && echo "  $(basename "$d")：$(ls "$d" | wc -l) 个"; done
echo "  顶层：$(ls $OUT/*.docx 2>/dev/null | wc -l) 份"
