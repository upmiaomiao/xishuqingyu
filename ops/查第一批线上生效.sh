#!/usr/bin/env bash
# 只读：按真实路径核对第一批改动是否已由线上返回。
set -u
B=http://127.0.0.1:8011

probe() {
  local u="$1" s="$2" label="$3"
  local code hit
  code=$(curl -s -o /tmp/_p.txt -w '%{http_code}' "$B$u")
  hit=$(grep -c -- "$s" /tmp/_p.txt || true)
  printf "  HTTP %s  命中=%s  %s  (%s)\n" "$code" "$hit" "$label" "$u"
}

echo "===== 线上实际返回的内容里有没有新代码 ====="
probe /gen/static/gen_ui.js   "isComposing"    "编制页：输入法守卫"
probe /gen/static/gen_ui.js   "回车发送，Shift+回车换行" "编制页：占位提示"
probe /gen/static/gen_ui.js   "ge-prog-stage"  "编制页：新建报告复位进度条"
probe /gen/static/gen_ui.js   "sendSay"        "编制页：发送逻辑抽出（回车复用）"
probe /audit/static/audit_ui.js "au-na-note"   "审核页：不适用口径"
probe /audit/static/audit_ui.css "au-na-note"  "审核页：口径样式"
probe /static/js/main.js      "isComposing"    "问答页：输入法守卫"

echo
echo "===== /audit 页面引用的资源（确认路径）====="
curl -s "$B/audit" | grep -oE '(src|href)="[^"]+"' | head -8

echo
echo "===== 意见书交付件（含不适用口径）——用真实结果生成一次并查这句话 ====="
cd /home/test/xishu_qingyu_serve
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import json, os, sys
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
from xishu_pipeline import audit_docx
res_dir = "/data/eia_audit/_审核结果"
picked = None
for fn in sorted(os.listdir(res_dir)):
    if not fn.endswith(".json"):
        continue
    with open(os.path.join(res_dir, fn), encoding="utf-8") as f:
        r = json.load(f)
    if (r.get("统计") or {}).get("不适用"):
        picked = (fn, r); break
if not picked:
    print("  没有含『不适用』的结果，跳过"); raise SystemExit
fn, r = picked
blocks, meta = audit_docx.build_blocks(fn, r, [], None)
na = [b for b in blocks if b.get("k") == "p" and "关于「不适用」" in (b.get("t") or "")]
print("  结果文件：", fn)
print("  不适用条数：", (r.get("统计") or {}).get("不适用"))
print("  意见书里『关于不适用』段落数：", len(na))
if na:
    print("  正文：", na[0]["t"][:150])
PY
