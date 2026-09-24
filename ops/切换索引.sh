#!/bin/bash
# 把 index_v3 切换上线（归档旧索引，不删除），然后重启站点并自检。
#   用法：bash 切换索引.sh
set -e
TS=$(date +%Y%m%d_%H%M%S)
LIVE=/data/fagui_rag/index
NEW=${1:-/data/fagui_rag/index_v3b}
BAK=/data/fagui_rag/index.bak_before_标准与标题_$TS
PY=/home/test/fagui_serve/.venv/bin/python

echo "===== 1) 切换前体检新索引 ====="
test -f "$NEW/chunks.jsonl" || { echo "❌ 新索引不存在"; exit 1; }
test -f "$NEW/vectors.npy"  || { echo "❌ 新索引向量不存在"; exit 1; }
echo "  新索引块数：$(wc -l < "$NEW/chunks.jsonl")"
echo "  线上索引块数：$(wc -l < "$LIVE/chunks.jsonl")"
# 注意（2026-09-22 修）：这里原来把 /data/fagui_rag/index_v3 **写死**了，
# 而实际要切的目录是第 7 行 $NEW 给的 —— 传别的目录进来时，自检会去查一个不存在的老路径
# （index_v3 早被切走），于是必然 assert 失败，白吓一跳。改成跟着 $NEW 走。
NEW_DIR="$NEW" "$PY" - <<'PY'
import json, os, numpy as np
d = os.environ["NEW_DIR"]
n = sum(1 for _ in open(os.path.join(d, "chunks.jsonl"), encoding="utf-8"))
v = np.load(os.path.join(d, "vectors.npy"), mmap_mode="r")
print(f"  {d}: chunks={n}  vectors={v.shape}  一致：{'✅' if v.shape[0]==n else '❌'}")
assert v.shape[0] == n, "块数与向量数不一致，不能切换"
PY
echo "  meta.json:"; cat "$NEW/meta.json"

echo
echo "===== 2) 归档线上索引（mv，不删除）====="
mv "$LIVE" "$BAK"
echo "  旧索引 → $BAK"

echo
echo "===== 3) 新索引上位 ====="
mv "$NEW" "$LIVE"
echo "  index_v3 → /data/fagui_rag/index"
ls -l /data/fagui_rag/index/

echo
echo "===== 4) 重启站点 ====="
bash /home/test/安全重启8011.sh 2>&1 | tail -6

echo
echo "===== 5) 健康检查 + 索引加载行 ====="
for i in $(seq 1 12); do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8011/health || true)
  [ "$code" = "200" ] && { echo "  第 $i 次 /health = 200"; break; }
  sleep 3
done
grep -a "Retriever" /home/test/xishu_qingyu_serve/qa_8011.log | tail -3
echo "站点 pid：$(pgrep -f xishu_qingyu_qa.py | tr '\n' ' ')"
