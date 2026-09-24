#!/bin/bash
# 查 3 秒整的卡顿：谁堵住了事件循环
cd /home/test/xishu_qingyu_serve/xishu_pipeline
echo "=== 后台任务 / 定时器 / 生命周期钩子 / 线程池 ==="
grep -rn 'create_task\|on_event\|BackgroundTasks\|lifespan\|set_default_executor' . --include=*.py
echo "(以上为空 = 没有后台任务)"

echo
echo "=== 图谱文件 ==="
grep -n 'KG_PATH' config.py
ls -la "$(grep -oP 'KG_PATH\s*=\s*\K.*' config.py | head -1 | tr -d '"'"'"')" 2>/dev/null

echo
echo "=== 各文件行数 ==="
wc -l *.py | sort -n | tail -16

echo
echo "=== async def 里直接做的重活（没有 to_thread 的）==="
grep -n 'async def' *.py | wc -l
echo "async 路由共上面这么多；其中调用 to_thread 的："
grep -cn 'to_thread' *.py | grep -v ':0'
