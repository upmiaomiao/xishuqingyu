#!/bin/bash
echo "=== 模型服务自报家门 ==="
for p in 8000 8101 7860 7870 8010; do
  r=$(curl -s -m 4 http://127.0.0.1:$p/v1/models 2>/dev/null | head -c 260)
  printf "  %-5s %s\n" "$p" "${r:-（无响应/不是模型服务）}"
done
echo
echo "=== tmux 会话里挂着什么 ==="
tmux ls 2>/dev/null | while IFS=: read -r name rest; do
  echo "  —— $name ——"
  tmux capture-pane -p -t "$name" 2>/dev/null | grep -v '^$' | tail -6 | sed 's/^/    /'
done
echo
echo "=== 几个关键进程的完整命令行 ==="
for pid in 1634645 2622718 2186034 1027772 3389477 1642884; do
  cmd=$(tr '\0' ' ' < /proc/$pid/cmdline 2>/dev/null | cut -c1-190)
  [ -n "$cmd" ] && printf "  pid=%-8s %s\n" "$pid" "$cmd"
done
echo
echo "=== 吃满 GPU6/7 的那个训练是谁的 ==="
ls -la /data/zmj/ 2>/dev/null | head -8 | sed 's/^/  /'
echo "  —— mario-rl-integrity-20260921 目录 ——"
ls -la --time-style=+%F_%T /data/zmj/mario-rl-integrity-20260921/ 2>/dev/null | head -10 | sed 's/^/  /'
echo "  —— 训练日志尾 ——"
find /data/zmj/mario-rl-integrity-20260921 -name '*.log' -newermt '-1 day' 2>/dev/null | head -3 | while read f; do
  echo "    $f"; tail -4 "$f" 2>/dev/null | sed 's/^/      /'
done
echo
echo "=== 那两个长期驻留的 vLLM 是谁起的（父进程链）==="
for pid in 1634645 1642884 2622718 2623807; do
  ppid=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' ')
  pcmd=$(tr '\0' ' ' < /proc/$ppid/cmdline 2>/dev/null | cut -c1-90)
  printf "  pid=%-8s ← 父 %-8s %s\n" "$pid" "${ppid:-?}" "${pcmd:-$(ps -o comm= -p $ppid 2>/dev/null)}"
done
echo
echo "=== 8000 / 8101 服务起于何时（进程启动时间）==="
ps -eo pid,lstart,etime,args 2>/dev/null | grep -E 'vllm|swift-rl' | grep -v grep | cut -c1-150 | sed 's/^/  /'
