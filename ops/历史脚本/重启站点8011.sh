#!/bin/bash
# 重启 8011 站点：停 → 等真的退出 → 起 → 等 /health 通
D=/home/test/xishu_qingyu_serve
L=$D/launch_xishu_qingyu_qa_8011.sh
PIDF=$D/qa_8011.pid

echo "=== 重启前 ==="
echo "  pid 文件：$(cat $PIDF 2>/dev/null)"
echo "  实际监听：$(ss -tlnp 2>/dev/null | grep ':8011' | head -1)"

echo
echo "=== 停 ==="
bash $L stop

echo "=== 等待进程真正退出（最多 20 秒）==="
OLD=$(cat $PIDF 2>/dev/null)
for i in $(seq 1 20); do
  if ! kill -0 "$OLD" 2>/dev/null; then echo "  第 ${i}s：已退出"; break; fi
  sleep 1
done
if kill -0 "$OLD" 2>/dev/null; then
  echo "  SIGTERM 20 秒未退出，补 SIGKILL"
  kill -9 "$OLD" 2>/dev/null
  sleep 2
fi
echo "  端口 8011 现在：$(ss -tln 2>/dev/null | grep -c ':8011') 个监听"

echo
echo "=== 起 ==="
bash $L start

echo "=== 等 /health（最多 90 秒）==="
for i in $(seq 1 90); do
  if curl -fsS -m 3 http://127.0.0.1:8011/health >/tmp/h.json 2>/dev/null; then
    echo "  第 ${i}s 起来了：$(cat /tmp/h.json)"
    break
  fi
  sleep 1
done

echo
echo "=== 重启后 ==="
echo "  pid 文件：$(cat $PIDF 2>/dev/null)"
echo "  实际监听：$(ss -tlnp 2>/dev/null | grep ':8011' | head -1)"
echo "  健康：$(curl -fsS -m 5 http://127.0.0.1:8011/health || echo 失败)"
echo "  图谱：$(curl -fsS -m 10 http://127.0.0.1:8011/kg/stats | head -c 90)"
