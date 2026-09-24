#!/bin/bash
echo "=== 1. /doc 正向路径（可点开的引用卡片）==="
SRC="技术政策 环发[2001]199号/危险废物污染防治技术政策 环发[2001]199号.md"
ENC=$(/home/test/fagui_serve/.venv/bin/python -c "import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1]))" "$SRC")
echo "source: $SRC"
curl -s -D - -o /tmp/_doc.pdf -m 60 "http://127.0.0.1:8011/doc?source=$ENC" | grep -iE '^HTTP|content-type|content-disposition|content-length'
echo "--- 落盘字节与前 8 字节（应为 %PDF）---"
ls -l /tmp/_doc.pdf
head -c 8 /tmp/_doc.pdf | od -c | head -2
/home/test/fagui_serve/.venv/bin/python -c "
d=open('/tmp/_doc.pdf','rb').read()
print('  PDF 魔数:', d[:5])
print('  含 EOF 标记:', b'%%EOF' in d[-2048:])
"
rm -f /tmp/_doc.pdf

echo
echo "=== 2. 知识图谱接口（前端视图的数据源）==="
echo "--- /kg/stats ---"
curl -s -m 30 http://127.0.0.1:8011/kg/stats
echo
echo "--- /kg/search?query=危险废物 ---"
curl -s -m 30 "http://127.0.0.1:8011/kg/search?query=%E5%8D%B1%E9%99%A9%E5%BA%9F%E7%89%A9&depth=2&limit=20" \
  | /home/test/fagui_serve/.venv/bin/python -c "
import json,sys
d=json.load(sys.stdin)
print('  键:', sorted(d.keys()))
print('  nodes:', len(d.get('nodes') or []), ' links:', len(d.get('links') or []))
print('  matched:', d.get('matched'))
n=(d.get('nodes') or [])[:3]
for x in n: print('   节点样例:', json.dumps(x, ensure_ascii=False)[:150])
l=(d.get('links') or [])[:2]
for x in l: print('   边样例  :', json.dumps(x, ensure_ascii=False)[:150])
"

echo
echo "=== 3. 前端 JS 里知识图谱视图怎么用这些数据 ==="
grep -o "kgStats\|available\|kgGraph\|/kg/search\|/kg/stats\|kgView\|renderKg\|openKg" /home/test/xishu_qingyu_serve/frontend/index.html | sort | uniq -c
