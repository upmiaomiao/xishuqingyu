#!/bin/bash
# 只读：看一眼判据库在哪、里面有哪些文件、顶层结构长什么样
echo '=== 找判据库 ==='
for d in /data/判据库 /data/eia_audit/判据库 /home/test/判据库; do
  [ -d "$d" ] && echo "存在: $d"
done
find / -maxdepth 4 -type d -name '判据库' 2>/dev/null | head -5

DIR=$(find / -maxdepth 4 -type d -name '判据库' 2>/dev/null | head -1)
echo
echo "=== 用: $DIR ==="
ls -la "$DIR"

cat > /tmp/_看判据.py <<'PY'
import json, os, sys
d = sys.argv[1]
for n in sorted(os.listdir(d)):
    if not n.endswith('.json'):
        continue
    p = os.path.join(d, n)
    try:
        j = json.load(open(p, encoding='utf-8'))
    except Exception as e:
        print('%s 读取失败 %s' % (n, e)); continue
    size = os.path.getsize(p)
    if isinstance(j, dict):
        print('%-28s %8d B  顶层键: %s' % (n, size, list(j)[:12]))
    else:
        print('%-28s %8d B  列表 %d 项' % (n, size, len(j)))
PY
/home/test/fagui_serve/.venv/bin/python /tmp/_看判据.py "$DIR"
