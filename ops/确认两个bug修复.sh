#!/bin/bash
# 确认两个 bug 的修复已经落到线上。
set -e
D=/home/test/xishu_qingyu_serve
cd "$D"

echo "=== 1. 线上文件指纹 ==="
md5sum frontend/js/ask.js xishu_pipeline/pipeline.py

echo
echo "=== 2. ask.js 里两处修复的标记 ==="
echo -n "  buildHistory 出现次数："
grep -c 'buildHistory' frontend/js/ask.js
echo -n "  closeRunningSteps 出现次数："
grep -c 'closeRunningSteps' frontend/js/ask.js
echo "  图片轮剔除逻辑："
grep -n "m.role === 'user' && m.image" frontend/js/ask.js | head -2
echo "  流结束收尾："
grep -n 'closeRunningSteps(am' frontend/js/ask.js

echo
echo "=== 3. pipeline.py 里补齐的 done ==="
grep -n '意图已识别\|回答已生成' xishu_pipeline/pipeline.py

echo
echo "=== 4. 服务状态 ==="
echo "  pid: $(cat qa_8011.pid 2>/dev/null)"
curl -fsS -m 5 http://127.0.0.1:8011/health && echo
curl -s -m 5 -o /dev/null -w '  GET / -> %{http_code}\n' http://127.0.0.1:8011/
