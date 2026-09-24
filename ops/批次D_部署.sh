#!/bin/bash
# 批次 D 服务端：先语法/导入检查再重启。
# 用**启动器自己的解释器**做检查 —— 裸 python3 没装 httpx，
# 拿它检查会得到一个和本次改动毫无关系的 ModuleNotFoundError（第一版就踩了）。
cd /home/test/xishu_qingyu_serve
PY=$(grep -oP '^\s*PYTHON=\K.*' launch_xishu_qingyu_qa_8011.sh | head -1 | tr -d '"'"'"'')
[ -x "$PY" ] || PY=$(command -v python3)
echo "解释器：$PY"

echo "--- py_compile ---"
"$PY" -c "
import py_compile
for f in ('xishu_pipeline/kg.py', 'xishu_pipeline/routes.py'):
    py_compile.compile(f, doraise=True)
    print('  OK', f)
" || exit 1

echo "--- 导入检查（py_compile 查不出没导入的名字）---"
"$PY" -c "
from xishu_pipeline.routes import app, find_entities
print('  routes 导入成功，find_entities 可调用：', callable(find_entities))
print('  /kg/entities 已注册：', any(getattr(r, 'path', '') == '/kg/entities' for r in app.routes))
" || exit 1

echo "--- 重启 ---"
bash /home/test/安全重启8011.sh
