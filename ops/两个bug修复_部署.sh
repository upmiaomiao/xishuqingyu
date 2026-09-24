#!/bin/bash
# 部署「图片串轮 + 转圈不停」两个 bug 的修复（2026-09-18）。
#
# 改了两个文件：
#   frontend/js/ask.js                  buildHistory 剔除图片轮 / 流结束收尾步骤
#   xishu_pipeline/pipeline.py          补齐 intent、generate 的 done 事件
#
# 注意：必须用 venv 里的 python 做导入检查（裸 python3 没有 httpx，
# 上一次就因为它在 set -e 下中断、连重启都没跑到）。
set -e

SITE=/home/test/xishu_qingyu_serve
ARCH=/home/test/_重构归档_20260918/两个bug修复_前
STAMP=$(date +%Y%m%d_%H%M%S)

echo "=== 1. 备份改前文件 ==="
mkdir -p "$ARCH"
for f in frontend/js/ask.js xishu_pipeline/pipeline.py; do
  if [ -f "$SITE/$f" ]; then
    cp -a "$SITE/$f" "$ARCH/$(basename $f).$STAMP"
    echo "  备份 $f -> $ARCH/$(basename $f).$STAMP"
  fi
done

echo
echo "=== 2. 语法检查 ==="
PYTHON=$(grep -oP '^\s*PYTHON=\K.*' /home/test/launch_xishu_qingyu_qa_8011.sh | tr -d '"'"'"'')
if [ -z "$PYTHON" ]; then PYTHON=/home/test/fagui_serve/.venv/bin/python; fi
echo "  用解释器：$PYTHON"
$PYTHON -m py_compile "$SITE/xishu_pipeline/pipeline.py"
echo "  py_compile OK"

echo
echo "=== 3. 导入检查（语法过不代表能导入 —— 曾经在这上面翻过车）==="
cd "$SITE"
$PYTHON -c "
import importlib, sys
m = importlib.import_module('xishu_pipeline.pipeline')
print('  导入 xishu_pipeline.pipeline OK')
import inspect
src = inspect.getsource(m)
n = src.count('\"state\": \"done\"')
print('  done 事件出现 %d 次' % n)
assert '意图已识别' in src, '缺 intent 的 done'
assert src.count('回答已生成') == 3, 'generate 的 done 应出现 3 处（direct/general/rag）'
print('  intent/generate 的 done 都已就位')
"

echo
echo "=== 4. 重启服务 ==="
pkill -f 'xishu_qingyu_serve' 2>/dev/null || true
sleep 2
cd /home/test
nohup ./launch_xishu_qingyu_qa_8011.sh > /dev/null 2>&1 &
sleep 6
NEWPID=$(pgrep -f 'xishu_qingyu_serve' | head -1)
echo "  新 pid：${NEWPID:-未起来！}"

echo
echo "=== 5. 探活 ==="
for i in 1 2 3 4 5 6 7 8 9 10; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 http://127.0.0.1:8011/ || true)
  if [ "$code" = "200" ]; then echo "  / -> 200（第 $i 次探测）"; break; fi
  sleep 2
done
curl -s --max-time 5 http://127.0.0.1:8011/kg/stats | head -c 120
echo
echo "=== 部署完成 ==="
