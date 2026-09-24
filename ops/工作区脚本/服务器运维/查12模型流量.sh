#!/bin/bash
echo "=== .12 上到 8000 / 8101 的已建立连接（有客户端在连吗）==="
ss -tn state established 2>/dev/null | awk 'NR==1 || /:8000|:8101/' | sed 's/^/  /'
echo "  （上面没有 8000/8101 行 = 当前没人连）"
echo
echo "=== 两个 vLLM 的输出去向（日志文件）==="
for pid in 1634645 2622718; do
  out=$(readlink /proc/$pid/fd/1 2>/dev/null)
  echo "  pid=$pid stdout → $out"
done
echo
echo "=== 这些日志最后 6 行（能看出最近有没有请求）==="
for f in $(for pid in 1634645 2622718; do readlink /proc/$pid/fd/1 2>/dev/null; done | grep -v '^/dev' | sort -u); do
  echo "  —— $f ——"
  tail -6 "$f" 2>/dev/null | cut -c1-170 | sed 's/^/    /'
done
echo
echo "=== 今天(09-24)有没有请求打到这两个端口（按日志里的时间戳数）==="
for f in $(for pid in 1634645 2622718; do readlink /proc/$pid/fd/1 2>/dev/null; done | grep -v '^/dev' | sort -u); do
  n=$(grep -c "09-24" "$f" 2>/dev/null)
  req=$(grep -cE 'POST /v1/(chat/completions|completions|rerank|embeddings)' "$f" 2>/dev/null)
  echo "  $f  今日行数=$n  累计请求行=$req"
done
echo
echo "=== xishu-qingyu-v5 在 .12 上有没有被引用（谁在连它）==="
grep -rl "10.201.31.12:8000" /home/test/*/  2>/dev/null | head -5 | sed 's/^/  /'
grep -rn "10.201.31.12:8000" /home/test/*.sh /home/test/*/*.sh 2>/dev/null | head -5 | sed 's/^/  /'
