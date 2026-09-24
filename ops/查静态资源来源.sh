#!/usr/bin/env bash
cd /home/test/xishu_qingyu_serve
echo "===== /static 挂在哪 ====="
python3 - <<'EOF'
import re, pathlib
for f in ("xishu_qingyu_qa.py", "xishu_pipeline/routes.py"):
    t = pathlib.Path(f).read_text(encoding="utf-8", errors="replace")
    for i, line in enumerate(t.splitlines(), 1):
        if "StaticFiles" in line or "mount(" in line:
            print(f"{f}:{i}: {line.strip()}")
EOF
ls -la static 2>/dev/null | head -3
echo
echo "===== 磁盘上的两个候选 ====="
md5sum frontend/js/message.js xishu_pipeline/static/js/message.js 2>/dev/null
ls -la frontend/js/message.js xishu_pipeline/static/js/message.js 2>/dev/null
echo
echo "===== HTTP 实际拿到的字节（带压缩协商） ====="
curl -s http://127.0.0.1:8011/static/js/message.js        | wc -c
curl -s --compressed http://127.0.0.1:8011/static/js/message.js | wc -c
curl -sI http://127.0.0.1:8011/static/js/message.js | grep -iE 'content-length|content-encoding|etag|last-modified'
echo
echo "===== 拿到的内容里有新逻辑吗 ====="
curl -s --compressed http://127.0.0.1:8011/static/js/message.js | grep -c 'probeDocInfo'
curl -s --compressed http://127.0.0.1:8011/static/js/message.js | grep -c '查看原文（文本版）'
