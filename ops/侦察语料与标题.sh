#!/bin/bash
# 侦察：语料源头(okf_bundles)结构、标题来源、焚烧标准缺口、入库脚本行为
set -u
OKF=/data/fagui_rag/okf_bundles
echo "===== 1) okf_bundles 顶层构成 ====="
ls "$OKF" | head -15
echo "--- 各类文档数 ---"
for d in "$OKF"/*/; do printf "  %6s  %s\n" "$(find "$d" -name '*.md' | wc -l)" "$(basename "$d")"; done

echo
echo "===== 2) 一份「标题烂」的报告 md 的前 18 行（front matter）====="
f=$(grep -rl '^title: *环境影响报告书 *$' "$OKF" 2>/dev/null | head -1)
echo "文件：$f"
head -18 "$f" 2>/dev/null

echo
echo "===== 3) 有多少 md 的 front matter title 是通用词 ====="
for t in "环境影响报告书" "环境影响报告书 （信息公开版）" "一、建设项目基本情况"; do
  printf "  title=%-28s %s 份\n" "$t" "$(grep -rl "^title: *$t *$" "$OKF" 2>/dev/null | wc -l)"
done
echo "  （对比）title 是标准本体的："
grep -rl '^title: .*污染控制标准' "$OKF" 2>/dev/null | head -8

echo
echo "===== 4) 焚烧类标准本体在不在 okf_bundles ====="
for k in 18485 18484 16889 1134; do
  printf "  %-6s 文件名命中：%s\n" "$k" "$(find "$OKF" -iname "*$k*" | wc -l)"
done
echo "  含『生活垃圾焚烧污染控制标准』的文件名："
find "$OKF" -iname '*生活垃圾焚烧污染控制*' | head -5
echo "  含『危险废物焚烧污染控制标准』的文件名："
find "$OKF" -iname '*危险废物焚烧污染控制*' | head -5

echo
echo "===== 5) 已废止的块来自哪些文档（前 10）====="
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import json
from collections import Counter
c = Counter()
with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as f:
    for line in f:
        d = json.loads(line)
        if d.get("status") == "已废止":
            c[d.get("source") or "?"] += 1
print(f"  已废止块合计 {sum(c.values())}，来自 {len(c)} 份文档")
for k, v in c.most_common(10):
    print(f"   {v:>5}  {k}")
PY

echo
echo "===== 6) 入库脚本：是否全量重建、标题从哪来 ====="
grep -n "title\|def \|jsonl\|vectors\|np.save\|for .*md\|glob" /data/fagui_rag/ingest_okf.py | head -40
echo "--- 行数 ---"
wc -l /data/fagui_rag/ingest_okf.py
