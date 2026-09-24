#!/usr/bin/env bash
# 文本清洗修复部署：先备份（可验证），再切换，再真 import 检查。重启是单独一步。
set -eu

LIVE=/home/test/xishu_qingyu_serve/xishu_pipeline/textclean.py
STAGE=/data/fagui_rag/_staging/textclean_v2.py
PY=/home/test/fagui_serve/.venv/bin/python
STAMP=$(date +%Y%m%d_%H%M%S)
BAK=/home/test/_重构归档_20260919/文本清洗_前

echo "===== 0) 前置检查（候选版语法 + import + 公式还原自检） ====="
test -f "$STAGE" || { echo "候选文件不存在，中止"; exit 1; }
"$PY" -m py_compile "$STAGE" && echo "候选版语法 OK"
cd /home/test/xishu_qingyu_serve
"$PY" - <<'EOF'
import importlib.util
spec = importlib.util.spec_from_file_location("tc_new", "/data/fagui_rag/_staging/textclean_v2.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
s = "不大于$1.0{\\times}10^{-5}\\,\\mathrm{cm/s}$，且厚度不小于$0.75~\\mathrm{m}$"
out = m.clean_retrieved_text(s)
print("import OK；公式还原自检 →", out)
assert "1.0×10⁻⁵" in out and "cm/s" in out and "0.75" in out, "公式还原失败"
print("自检通过")
EOF

echo
echo "===== 1) 备份线上文件 ====="
mkdir -p "$BAK"
cp -p "$LIVE" "$BAK/textclean.py.$STAMP"
md5sum "$BAK/textclean.py.$STAMP" "$LIVE"
cmp -s "$BAK/textclean.py.$STAMP" "$LIVE" || { echo "备份不一致，中止"; exit 1; }
echo "备份校验通过"

echo
echo "===== 2) 切换 ====="
cp "$STAGE" "$LIVE"
"$PY" -m py_compile "$LIVE" && echo "线上文件语法 OK"
md5sum "$LIVE" "$STAGE"

echo
echo "===== 3) 站点包真实 import（在站点目录下，按包路径导入） ====="
"$PY" - <<'EOF'
import sys
sys.path.insert(0, "/home/test/xishu_qingyu_serve")
from xishu_pipeline.textclean import clean_retrieved_text, demath
s = "饱和渗透系数不大于$1.0{\\times}10^{-5}\\,\\mathrm{cm/s}$"
print("站点包 import OK →", clean_retrieved_text(s))
EOF

echo
echo "===== 4) 归档目录 ====="
ls -la "$BAK"
