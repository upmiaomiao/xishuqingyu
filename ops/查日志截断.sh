#!/bin/bash
# 查启动器怎么处理日志 + 日志为什么这么小
D=/home/test/xishu_qingyu_serve
L=$D/launch_xishu_qingyu_qa_8011.sh

echo "=========== 1. 启动器里跟日志有关的行 ==========="
grep -n 'LOG_FILE\|nohup\|2>&1\|>>\|> *"\$' "$L" | sed 's/^/  /'

echo
echo "=========== 2. start 分支原文 ==========="
awk '/^start\)|^ *start\)/,/^ *;;/' "$L" | head -40 | sed 's/^/  /'

echo
echo "=========== 3. qa_8011.log 全文 ==========="
wc -c "$D/qa_8011.log"
echo "  --- 内容 ---"
cat "$D/qa_8011.log" | sed 's/^/  /'

echo
echo "=========== 4. 目录下所有 log ==========="
ls -la "$D" | grep -i log | sed 's/^/  /'

echo
echo "=========== 5. uvicorn 的 access log 开没开 ==========="
grep -rn 'access_log\|log_level\|uvicorn.run' "$D/xishu_qingyu_qa.py" 2>/dev/null | sed 's/^/  /'

echo
echo "=========== 6. 系统里还有没有别的访问日志（按 09:48 找）==========="
for f in /var/log/nginx/access.log /home/test/*.access.log; do
  [ -f "$f" ] && { echo "  --- $f ---"; grep -c '09:48' "$f" 2>/dev/null; }
done
echo "  当前监听 8011 的进程："
ss -ltnp 2>/dev/null | grep 8011 | sed 's/^/    /'
