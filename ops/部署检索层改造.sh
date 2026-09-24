#!/usr/bin/env bash
# 检索层改造部署：先备份（可验证），再切换。不做重启——重启是单独一步。
set -eu

LIVE=/data/fagui_rag/retriever.py
STAGE=/data/fagui_rag/_staging/retriever_v2.py
PY=/home/test/fagui_serve/.venv/bin/python
STAMP=$(date +%Y%m%d_%H%M%S)
BAK=/home/test/_重构归档_20260919/检索层改造_前

echo "===== 0) 前置检查 ====="
test -f "$STAGE" || { echo "候选文件不存在，中止"; exit 1; }
"$PY" -m py_compile "$STAGE" && echo "候选版语法 OK"
"$PY" - <<'EOF'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("rv2check", "/data/fagui_rag/_staging/retriever_v2.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)          # 真 import（会执行模块级 re.compile）
print("候选版 import OK；doc_key 自检：",
      m.doc_key("环评报告/A 项目 copy.md") == m.doc_key("环评报告/A 项目.md"),
      "| auth_need(限值问题)=", m.auth_need("二噁英的排放限值是多少？"))
EOF

echo
echo "===== 1) 备份线上文件（这一步成功才继续） ====="
mkdir -p "$BAK"
cp -p "$LIVE" "$BAK/retriever.py.$STAMP"
echo "备份文件：$BAK/retriever.py.$STAMP"
md5sum "$BAK/retriever.py.$STAMP" "$LIVE"
if ! cmp -s "$BAK/retriever.py.$STAMP" "$LIVE"; then
  echo "备份与线上不一致，中止"; exit 1
fi
echo "备份校验通过（与线上逐字节一致）"

echo
echo "===== 2) 切换 ====="
cp "$STAGE" "$LIVE"
"$PY" -m py_compile "$LIVE" && echo "线上文件语法 OK"
echo "切换后："
md5sum "$LIVE" "$STAGE"
ls -la "$LIVE"

echo
echo "===== 3) 归档目录现状 ====="
ls -la "$BAK"
