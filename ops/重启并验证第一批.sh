#!/usr/bin/env bash
# 重启 8011 并核验健康 + 关键模块版本（第一批修复上线后半程）。
set -u
echo "===== 1) 重启 ====="
bash /home/test/安全重启8011.sh 2>&1 | tail -12

echo
echo "===== 2) 健康检查 ====="
for i in $(seq 1 30); do
  code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health || true)
  if [ "$code" = "200" ]; then echo "  /health 200（第 $i 次轮询）"; break; fi
  sleep 2
done
curl -s http://127.0.0.1:8011/health; echo

echo
echo "===== 3) 静态资源是否已是新版（按特征串查线上实际返回）====="
check_str() {
  local url="$1" needle="$2" label="$3"
  if curl -s "$url" | grep -q -- "$needle"; then echo "  [有] $label"; else echo "  [缺] $label  ← $url"; fi
}
check_str http://127.0.0.1:8011/xishu_pipeline/static/gen_ui.js "isComposing" "编制页输入法守卫"
check_str http://127.0.0.1:8011/xishu_pipeline/static/gen_ui.js "ge-count" "新建报告复位 ge-count"
check_str http://127.0.0.1:8011/frontend/js/main.js "isComposing" "问答页输入法守卫"
check_str http://127.0.0.1:8011/xishu_pipeline/static/audit_ui.js "au-na-note" "审核界面不适用口径"
check_str http://127.0.0.1:8011/xishu_pipeline/static/audit_ui.css "au-na-note" "口径样式"

echo
echo "===== 4) 判定引擎端到端（不写盘、不改已有结果）====="
cd /data/eia_audit
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "/data/eia_audit")
from audit.runner import audit_file
import urllib.request
names = json.load(urllib.request.urlopen("http://127.0.0.1:8011/audit/api/reports", timeout=30))
if isinstance(names, dict):
    names = names.get("reports") or names.get("files") or []
picked = [n if isinstance(n, str) else (n.get("name") or n.get("file")) for n in names]
print("  报告清单：", len(picked), "份")
KEY = ("环境风险专项评价设置", "大气专项评价设置")
for name in picked:
    p = os.path.join("/data/eia_reports", name)
    if not os.path.isfile(p):
        continue
    try:
        res = audit_file(p, use_llm=False)
    except Exception as exc:
        print("  !! %s 跑失败：%s" % (name[:28], exc)); continue
    rows = [it for it in res["items"] if it.get("审核项") in KEY]
    if not rows:
        continue
    for it in rows:
        print("  %-26s %-14s %-8s %s" % (name[:26], it["审核项"], it["AI审核"],
                                         (it.get("理由") or "")[:70]))
PY
