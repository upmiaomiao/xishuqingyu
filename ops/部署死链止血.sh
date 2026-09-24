#!/usr/bin/env bash
# 「查看原文」死链止血部署：后端加 /doc/info_batch，前端按钮按探测结果说实话。
# 静态文件（js）即时生效；routes.py 需要重启才生效（重启单独一步）。
set -eu

LIVE=/home/test/xishu_qingyu_serve
STAGE=/home/test/_staging_死链止血
PY=/home/test/fagui_serve/.venv/bin/python
STAMP=$(date +%Y%m%d_%H%M%S)
BAK=/home/test/_重构归档_20260919/死链止血_前

echo "===== 0) 候选文件语法检查 ====="
test -f "$STAGE/routes.py" || { echo "候选 routes.py 不存在，中止"; exit 1; }
"$PY" -m py_compile "$STAGE/routes.py" && echo "候选 routes.py 语法 OK"
ls -la "$STAGE"

echo
echo "===== 1) 备份线上文件 ====="
mkdir -p "$BAK"
cp -p "$LIVE/xishu_pipeline/routes.py"          "$BAK/routes.py.$STAMP"
cp -p "$LIVE/frontend/js/message.js"            "$BAK/message.js.$STAMP"
cp -p "$LIVE/frontend/js/ask.js"                "$BAK/ask.js.$STAMP"
cmp -s "$BAK/routes.py.$STAMP"   "$LIVE/xishu_pipeline/routes.py"   || { echo "routes 备份不一致，中止"; exit 1; }
cmp -s "$BAK/message.js.$STAMP"  "$LIVE/frontend/js/message.js"     || { echo "message 备份不一致，中止"; exit 1; }
cmp -s "$BAK/ask.js.$STAMP"      "$LIVE/frontend/js/ask.js"         || { echo "ask 备份不一致，中止"; exit 1; }
echo "备份校验通过："
md5sum "$BAK"/*."$STAMP"

echo
echo "===== 2) 切换 ====="
cp "$STAGE/routes.py"   "$LIVE/xishu_pipeline/routes.py"
cp "$STAGE/message.js"  "$LIVE/frontend/js/message.js"
cp "$STAGE/ask.js"      "$LIVE/frontend/js/ask.js"
"$PY" -m py_compile "$LIVE/xishu_pipeline/routes.py" && echo "线上 routes.py 语法 OK"

echo
echo "===== 3) 真实 import（会连带加载 config/kg/pipeline/retriever）====="
cd "$LIVE"
"$PY" - <<'EOF'
import sys
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
from xishu_pipeline.routes import app
paths = sorted({r.path for r in app.routes if getattr(r, "path", "").startswith("/doc")})
print("import OK；/doc 系列路由：", paths)
assert "/doc/info_batch" in paths, "/doc/info_batch 没注册上"
print("路由自检通过")
EOF

echo
echo "===== 4) 文件指纹 ====="
md5sum "$LIVE/xishu_pipeline/routes.py" "$LIVE/frontend/js/message.js" "$LIVE/frontend/js/ask.js"
