#!/usr/bin/env bash
# 全量入库后的完整验证，结果写日志（避免 SSH 掉线丢输出）
set -u
R=/data/fagui_rag
PY=/home/test/fagui_serve/.venv/bin/python
LOG=/tmp/verify_eia.log

{
echo "########## 0) 备份清单"
ls -d "$R"/index.bak* "$R"/okf_bundles.bak* 2>/dev/null
df -h /data | tail -1

echo
echo "########## 1) 索引与语料分布"
echo "chunks: $(wc -l < "$R/index/chunks.jsonl")  files: $(cat "$R/index/meta.json" | grep total_files)"
python3 - <<'PY'
import json
from collections import Counter
c = Counter()
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        c[o.get("source", "").split("/")[0]] += 1
for k, v in c.most_common():
    print(f"  {k}: {v}")
PY

echo
echo "########## 2) 回归基线（8011）"
cd /tmp && $PY /tmp/网站_回归基线.py --base http://127.0.0.1:8011 2>&1 | tail -6

echo
echo "########## 3) 稀释对照：标准/导则问题里报告语料占几条"
for q in "一般工业固体废物贮存场 I 类场的防渗要求是什么？" \
         "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？" \
         "大气环境影响评价的评价等级是怎么判定的？" \
         "生活垃圾焚烧烟气中二噁英的排放限值是多少？" \
         "危险废物的鉴别标准是什么？"; do
  echo "-- $q"
  $PY /tmp/查检索结果.py "$q" --top-k 5 2>&1 | grep -e '^\[[0-9]' -e '^    [^ ]' | head -11
done

echo
echo "########## 4) 报告类问题应命中报告语料"
$PY /tmp/查检索结果.py "郑州市金水河综合整治工程的环境影响评价结论是什么？" --top-k 3 2>&1 | grep -e '^\[[0-9]' -e '环评报告' | head -8

echo
echo "########## 5) /doc 对报告来源的行为（报告无 PDF）"
SRC=$(python3 -c "
import json
with open('/data/fagui_rag/index/chunks.jsonl', encoding='utf-8') as f:
    for line in f:
        o = json.loads(line)
        if o.get('source','').startswith('环评报告/'):
            print(o['source']); break
")
echo "样例 source: $SRC"
python3 - "$SRC" <<'PY'
import sys, urllib.parse, urllib.request, urllib.error
src = sys.argv[1]
url = "http://127.0.0.1:8011/doc?source=" + urllib.parse.quote(src)
try:
    with urllib.request.urlopen(url, timeout=30) as r:
        print("HTTP", r.status, r.headers.get("content-type"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode("utf-8", "replace")[:160])
PY
echo "########## 完成"
} > "$LOG" 2>&1
echo "日志已写 $LOG"
