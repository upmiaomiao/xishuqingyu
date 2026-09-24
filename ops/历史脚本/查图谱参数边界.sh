#!/bin/bash
echo "=== KG_MAX_SUBGRAPH_NODES ==="
grep -n 'KG_MAX_SUBGRAPH_NODES' /home/test/xishu_qingyu_serve/xishu_pipeline/config.py

echo
echo "=== 前端实际用的那条 URL（index.html:85 逐字）==="
U='http://127.0.0.1:8011/kg/search?query=%E5%8D%B1%E9%99%A9%E5%BA%9F%E7%89%A9&depth=1&limit=70'
echo "  $U"
curl -s -o /dev/null -w "  → HTTP %{http_code}\n" -m 30 "$U"

echo
echo "=== 参数边界逐项复核 ==="
check() {
  code=$(curl -s -o /dev/null -w '%{http_code}' -m 20 "http://127.0.0.1:8011/kg/search?query=x&$1")
  printf '  %-24s -> %s\n' "$1" "$code"
}
check 'depth=1&limit=70'      # 前端在用
check 'depth=0&limit=10'      # 下限
check 'depth=2&limit=200'     # 上限附近
check 'depth=1&limit=9'       # 低于 limit 下限
check 'depth=3&limit=70'      # 高于 depth 上限
check 'depth=1&limit=201'     # 高于 limit 上限

echo
echo "=== /kg/stats 在 available:false 时会返回什么（模拟前端取值）==="
echo "  前端代码：d.nodes.toLocaleString() + d.links.toLocaleString()，且**不检查 d.available**"
echo "  服务端：available = bool(graph['nodes'])，labels 恒存在（可能为空 dict）"
echo "  → 图谱文件一旦丢失，页面显示「0 个节点 · 0 条关系」，无任何告警"
