#!/usr/bin/env bash
# 影子实例（8012）完整验证：重排后重启 → 基线回归 → 限值问答 A/B → 引用去重。
# 线上 8011 全程不动。
set -u
PORT=8012
OLD=http://127.0.0.1:8011
NEW=http://127.0.0.1:$PORT

echo "==== 1) 重启影子实例（加载新索引）"
fuser -k -n tcp $PORT >/dev/null 2>&1 || true
sleep 2
bash /tmp/起影子.sh /data/fagui_rag/index_stage $PORT
echo

echo "==== 2) 影子实例健康与索引规模"
curl -fsS "$NEW/health"; echo
grep -e Retriever /tmp/shadow_${PORT}.log | tail -1
echo

echo "==== 3) 回归基线（结构与路由断言）"
python3 /tmp/网站_回归基线.py --base "$NEW" 2>&1 | tail -20
echo

echo "==== 4) 引用去重单测"
/home/test/fagui_serve/.venv/bin/python /tmp/检索去重单测.py /data/fagui_rag 2>&1 | tail -6
echo

echo "==== 5) 限值问答 A/B（旧 8011 vs 新 $PORT）"
python3 /tmp/AB对比.py --old "$OLD" --new "$NEW" 2>&1 | tail -45
