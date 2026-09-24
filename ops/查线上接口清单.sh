#!/usr/bin/env bash
# 线上接口清单 + 关键文件指纹（用来核对文档里写的接口/路径是不是还成立）
cd /home/test/xishu_qingyu_serve || exit 1
echo "=== 启动器指纹（文档记的是 fdabd26175e125d4d0ca62ac4abffce1）==="
md5sum launch_xishu_qingyu_qa_8011.sh
echo
echo "=== 注册的接口（qa.py 内联）==="
grep -nE '@app\.(get|post|put|delete)\(' xishu_qingyu_qa.py | sed 's/^/  /'
echo
echo "=== 注册的接口（路由模块）==="
for f in xishu_pipeline/routes.py xishu_pipeline/audit_routes.py xishu_pipeline/gen_routes.py; do
  [ -f "$f" ] || continue
  echo "--- $f"
  grep -nE '\.(get|post)\(' "$f" | head -20 | sed 's/^/  /'
done
echo
echo "=== 前端真正调用的接口（从 js 里抽）==="
grep -rhoE "'/(doc|hybrid_search|ask|audit|gen|kg|health)[a-z_/]*'" frontend/js/*.js frontend/*.html 2>/dev/null | sort | uniq -c | sort -nr | head -20
