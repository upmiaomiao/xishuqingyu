#!/bin/bash
# 部署「原文批注视图」第 2 步：导入自检 → 重启 → 健康检查（上传之后跑）。
set -u
S=/home/test/xishu_qingyu_serve
PY=/home/test/fagui_serve/.venv/bin/python

echo "=== 1) 导入自检（不改动运行中的进程）==="
cd /home/test || exit 1
$PY - <<'PYEOF'
import sys
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
try:
    from xishu_pipeline import audit_anchor, audit_routes
    print("  导入 OK：audit_routes / audit_anchor")
    for p in sorted(r.path for r in audit_routes.router.routes):
        if "annot" in p or "/page/" in p or "pageimg" in p or "download" in p:
            print("  路由：", p)
    print("  静态白名单：", sorted(audit_routes.STATIC_OK))
    print("  定位档位：", list(audit_anchor.LEVELS))
except Exception:
    import traceback
    traceback.print_exc()
    sys.exit(3)
PYEOF
rc=$?
if [ "$rc" != "0" ]; then
  echo "❌ 导入自检失败（返回码 $rc）—— **不重启**，线上仍是旧代码"
  exit $rc
fi

echo
echo "=== 2) 重启站点（安全重启8011.sh）==="
bash /home/test/安全重启8011.sh
sleep 6
echo
echo "=== 3) 健康检查 ==="
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /tmp/_h.txt -w '%{http_code}' -m 5 http://127.0.0.1:8011/health || echo 000)
  if [ "$code" = "200" ]; then break; fi
  sleep 2
done
echo "  /health → $code"
cat /tmp/_h.txt; echo
echo "  pid: $(cat $S/qa_8011.pid 2>/dev/null)"
echo
echo "=== 4) 静态资源可达性 ==="
for u in /audit/static/audit_ui.js /audit/static/audit_doc.js /audit/static/audit_ui.css; do
  echo "  $u → $(curl -s -o /dev/null -w '%{http_code} %{size_download}B' -m 8 http://127.0.0.1:8011$u)"
done
echo
echo "=== 5) 新接口抽查（临沂报告）==="
N=$(python3 - <<'PY'
import json,glob,os
for f in glob.glob('/data/eia_audit/_审核结果/*.json'):
    d=json.load(open(f,encoding='utf-8'))
    if 'items' in d and '临沂' in d.get('file',{}).get('name',''):
        print(d['file']['name']); break
PY
)
echo "  报告：$N"
curl -s -m 120 --get --data-urlencode "parse=0" \
  "http://127.0.0.1:8011/audit/api/annot/$(python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$N")" \
  -o /tmp/_annot.json -w '  /annot → %{http_code} %{size_download}B\n'
python3 - <<'PY'
import json
d = json.load(open('/tmp/_annot.json', encoding='utf-8'))
if d.get('ok'):
    print('  页数', d.get('pages'), '批注', len(d.get('anchors') or []), '定位统计', d.get('定位统计'))
    print('  目录条目', len(d.get('toc') or []))
else:
    print('  返回：', json.dumps(d, ensure_ascii=False)[:300])
PY
