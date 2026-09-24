#!/usr/bin/env bash
# B 步入库后验证：索引规模 + 语料分布 + 重启 8011 + 回归基线 + 稀释对照 + /doc 行为
set -u
R=/data/fagui_rag
PY=/home/test/fagui_serve/.venv/bin/python

echo "==== 1) 索引规模与语料分布 ===="
echo "chunks: $(wc -l < "$R/index/chunks.jsonl")"
echo "meta:"; cat "$R/index/meta.json" | head -8
du -sh "$R/index"

echo
echo "==== 2) 重启 8011 并核验 ===="
bash /tmp/重启8011.sh 2>&1 | tail -8

echo
echo "==== 3) 回归基线 ===="
cd /tmp && $PY /tmp/网站_回归基线.py --base http://127.0.0.1:8011 2>&1 | tail -5

echo
echo "==== 4) 稀释对照：标准/导则问题是否被报告语料挤掉 ===="
for q in "一般工业固体废物贮存场 I 类场的防渗要求是什么？" \
         "储油库大气污染物排放标准 GB 20950-2020 的排放限值是多少？" \
         "大气环境影响评价的评价等级是怎么判定的？" \
         "生活垃圾焚烧厂烟气中二噁英的排放限值是多少？"; do
  echo "-- $q"
  $PY /tmp/查检索结果.py "$q" --top-k 5 2>&1 \
    | grep -e '^\[[0-9]' -e '^    [^ ]' | head -12
done

echo
echo "==== 5) 报告类问题应命中报告语料 ===="
$PY /tmp/查检索结果.py "郑州市金水河综合整治工程的环境影响评价结论是什么？" --top-k 3 2>&1 \
  | grep -e '^\[[0-9]' -e '^    环评报告' | head -8

echo
echo "==== 6) /doc 对报告来源的行为（报告无 PDF，应给出明确 404） ===="
SRC=$(grep -o '"source": "环评报告/[^"]*"' "$R/index/chunks.jsonl" | head -1 | sed 's/.*: "//; s/"$//')
echo "样例 source: $SRC"
python3 - "$SRC" <<'PY'
import sys, urllib.parse, urllib.request, urllib.error
src = sys.argv[1]
url = "http://127.0.0.1:8011/doc?source=" + urllib.parse.quote(src)
try:
    with urllib.request.urlopen(url, timeout=30) as r:
        print("HTTP", r.status, r.headers.get("content-type"))
except urllib.error.HTTPError as e:
    print("HTTP", e.code, e.read().decode("utf-8", "replace")[:200])
PY
