#!/bin/bash
echo "=== 1. 日志里是否出现过「结构化渲染成功」的标记 ==="
echo "渲染成功时报告以【一、图片类型】开头；失败时以 ⚠️ 本次未能解析 开头"
for f in /home/test/xishu_qingyu_serve/*.log; do
  echo "[$f]"
  echo "  【一、图片类型】 : $(grep -c '【一、图片类型】' $f 2>/dev/null)"
  echo "  【三、核验清单】 : $(grep -c '【三、核验清单】' $f 2>/dev/null)"
  echo "  ⚠️ 未能解析     : $(grep -c '未能解析出结构化研判结果' $f 2>/dev/null)"
  echo "  json_parse_failed: $(grep -c 'json_parse_failed' $f 2>/dev/null)"
done

echo
echo "=== 2. 历史备份里的照片契约是否变过 ==="
for d in xishu_pipeline xishu_pipeline.bak_p1_20260916 xishu_pipeline.bak_p2_20260916 xishu_pipeline.bak_p3_20260916; do
  p=/home/test/xishu_qingyu_serve/$d/prompts.py
  c=/home/test/xishu_qingyu_serve/$d/compose.py
  if [ -f "$p" ]; then
    echo "[$d/prompts.py]  md5=$(md5sum $p | cut -c1-12)  PHOTO_JSON_CONTRACT 行数=$(grep -c 'PHOTO_JSON_CONTRACT' $p)"
  fi
  if [ -f "$c" ]; then
    echo "[$d/compose.py]  md5=$(md5sum $c | cut -c1-12)  photo_messages=$(grep -c 'def photo_messages' $c)"
  fi
done

echo
echo "=== 3. 模型是否支持 system 消息里的契约（看 chat template 是否吃 system）==="
grep -rn "photo_messages" /home/test/xishu_qingyu_serve/xishu_pipeline/pipeline.py

echo
echo "=== 4. 站点日志里最近一次 photo 请求的原始输出（找 raw 落盘或调试痕迹）==="
ls -la /home/test/xishu_qingyu_serve/*.log
