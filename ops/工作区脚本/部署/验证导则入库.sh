#!/usr/bin/env bash
# A 步验证：端口绑定唯一性 + 回归基线 + 导则正文可检索
set -u
PY=/home/test/fagui_serve/.venv/bin/python

echo "== port bindings (8011/8012) =="
ss -ltnp 2>/dev/null | grep -e ':8011' -e ':8012' || echo "(ss 无输出)"
echo
echo "== listening PIDs per port =="
for p in 8011 8012; do
  n=$(ss -ltn 2>/dev/null | grep -c ":$p ")
  echo "port $p listeners: $n"
done

echo
echo "== regression baseline on 8011 =="
cd /tmp && $PY /tmp/网站_回归基线.py --base http://127.0.0.1:8011 2>&1 | tail -8

echo
echo "== 导则正文检索（应命中环评导则语料） =="
for q in "大气环境影响评价的评价等级是怎么判定的？" \
         "地下水环境影响评价中Ⅰ类建设项目如何判定评价等级？" \
         "土壤环境影响评价的评价等级如何划分？"; do
  echo "-- $q"
  $PY /tmp/查检索结果.py "$q" --top-k 3 2>&1 | grep -e "rerank=" -e "环评导则" | head -6
done
