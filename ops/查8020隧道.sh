#!/bin/bash
echo "---- 谁在 .10:8020 ----"
ss -lntp 2>/dev/null | grep 8020
echo "---- 8020 自报家门 ----"
curl -s -m 4 http://127.0.0.1:8020/v1/models | head -c 140; echo
echo "---- 进程链 ----"
for p in $(ss -lntp 2>/dev/null | grep 8020 | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u); do
  echo "  pid=$p  $(ps -o user=,etime= -p $p)"
  tr '\0' ' ' < /proc/$p/cmdline | cut -c1-200; echo
  ppid=$(ps -o ppid= -p $p | tr -d ' ')
  echo "    父 pid=$ppid  $(tr '\0' ' ' < /proc/$ppid/cmdline 2>/dev/null | cut -c1-160)"
done
echo "---- 到 .12:8000 的连接 ----"
ss -tnp 2>/dev/null | grep -E ':8000' | head -5
echo "---- 站点进程打开的到 .12 的连接 ----"
ss -tnp 2>/dev/null | grep '10.201.31.12' | head -5
