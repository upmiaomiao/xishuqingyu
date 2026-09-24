#!/usr/bin/env bash
# 线上进程真正生效的配置：代码改了不算数，环境变量能把它整体关掉
echo "=== 8011 进程 ==="
pid=$(cat /home/test/xishu_qingyu_serve/qa_8011.pid 2>/dev/null)
ps -o pid,etime,cmd -p "$pid" | tail -1
echo
echo "=== 该进程环境里的 RAG_* / PYTHON* ==="
tr '\0' '\n' < /proc/"$pid"/environ 2>/dev/null | grep -E '^(RAG_|PYTHON|EMBED|RERANK)' || echo "（没有任何 RAG_* 覆盖 —— 用的是代码里的默认值）"
echo
echo "=== 站点 .env ==="
cat /home/test/xishu_qingyu_serve/.env 2>/dev/null | sed 's/=.*/=<省略值>/'
echo
echo "=== 启动脚本（冻结版）==="
cat /home/test/xishu_qingyu_serve/launch_xishu_qingyu_qa_8011.sh
echo
echo "=== 安全重启脚本 ==="
cat /home/test/安全重启8011.sh
echo
echo "=== 冒烟：真实问答一眼（确认改动的检索层确实在生效）==="
curl -s -m 60 "http://127.0.0.1:8011/api/ask_stream" -H 'Content-Type: application/json' \
  -d '{"question":"一般工业固体废物贮存场 I 类场的防渗要求是什么？","top_k":5}' 2>/dev/null | head -c 400
echo
