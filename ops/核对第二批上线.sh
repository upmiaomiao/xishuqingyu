#!/usr/bin/env bash
# 只读：上线后的最终状态核对
set -u
echo "===== 1) 健康检查 ====="
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:8011/health
pgrep -af 'xishu|uvicorn' | head -3

echo
echo "===== 2) 线上关键文件指纹（应与第二批记录一致）====="
md5sum /data/eia_audit/audit/extract.py \
       /data/eia_audit/audit/items_extra.py \
       /home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py \
       /home/test/xishu_qingyu_serve/xishu_pipeline/gen_routes.py \
       /home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js \
       /home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css

echo
echo "===== 3) 现用索引 ====="
ls -ld /data/fagui_rag/index
python - <<'PY'
import json
m = json.load(open("/data/fagui_rag/index/meta.json", encoding="utf-8"))
for k in ("built_at", "chunks_total", "chunks_restatus", "chunks_restatus_note", "chunks_retitled", "chunks_added"):
    print("  %-22s %s" % (k, m.get(k)))
PY

echo
echo "===== 4) 备份都在（归档不删）====="
ls -1 /home/test/_重构归档_20260922/第二批_前/*.2026* 2>/dev/null | head -8
ls -1d /data/fagui_rag/index.bak_* 2>/dev/null | tail -3
