#!/bin/bash
# 部署验证：备份核对 → 重启 → 新接口（归档/删除）→ 静态资源
D=/home/test/xishu_qingyu_serve
P=$D/xishu_pipeline
L=$D/launch_xishu_qingyu_qa_8011.sh
OUT=/data/eia_report_gen/_生成结果
ARC=$OUT/_已归档

echo "================ 1. 备份核对（应等于改动前的原版 md5）================"
echo "  期望 gen_routes.py  c7f10340fd47f4472493a184303af23c"
echo "  期望 gen_ui.js      5e230f5572cae1094d906cc63deae070"
echo "  期望 gen_ui.css     c66be3732661d7ef51f8431940aa06f1"
echo "  --- 实际 ---"
md5sum $P/gen_routes.py.bak_ui_20260918 $P/static/gen_ui.js.bak_ui_20260918 $P/static/gen_ui.css.bak_ui_20260918

echo
echo "================ 2. 新文件 md5（应等于本地）================"
echo "  期望 gen_routes.py  1f90d5240c9ecee9c019e6e55d2ef762"
echo "  期望 gen_ui.js      a4dab242bdd341229439ce1742cfaa01"
echo "  期望 gen_ui.css     6d7cc4ed3343deaabe434ae18eeeaa65"
echo "  --- 实际 ---"
md5sum $P/gen_routes.py $P/static/gen_ui.js $P/static/gen_ui.css

echo
echo "================ 3. 重启 8011 ================"
bash $L stop
OLD=$(cat $D/qa_8011.pid 2>/dev/null)
for i in $(seq 1 20); do kill -0 "$OLD" 2>/dev/null || { echo "  第 ${i}s 已退出"; break; }; sleep 1; done
kill -0 "$OLD" 2>/dev/null && { echo "  补 SIGKILL"; kill -9 "$OLD"; sleep 2; }
bash $L start
for i in $(seq 1 90); do
  curl -fsS -m 3 http://127.0.0.1:8011/health >/dev/null 2>&1 && { echo "  第 ${i}s /health 通"; break; }
  sleep 1
done

echo
echo "================ 4. 归档 / 删除 接口 ================"
PROBE="$OUT/_探针_归档删除.docx"
cp -p "$(ls -t $OUT/*.docx | head -1)" "$PROBE"
echo "  造一个探针文件：$(basename "$PROBE")  $(stat -c%s "$PROBE") 字节"

echo
echo "  --- 4.1 目录穿越应被挡住 ---"
for bad in '../../etc/passwd.docx' '/etc/passwd.docx' '_填报模板.json' '不存在.docx' ''; do
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' -m 20 -X POST http://127.0.0.1:8011/gen/api/archive \
         -H 'Content-Type: application/json' --data-binary "{\"name\":\"$bad\"}")
  printf '    archive %-26s -> %s  %s\n' "'$bad'" "$code" "$(head -c 60 /tmp/r.json)"
done

echo
echo "  --- 4.2 归档（应移进 _已归档/）---"
code=$(curl -s -o /tmp/r.json -w '%{http_code}' -m 30 -X POST http://127.0.0.1:8011/gen/api/archive \
       -H 'Content-Type: application/json' --data-binary '{"name":"_探针_归档删除.docx"}')
echo "    HTTP $code  $(cat /tmp/r.json)"
echo "    原位置还在吗：$([ -f "$PROBE" ] && echo '在（不对）' || echo '不在了（对）')"
echo "    归档目录里有吗：$(ls $ARC/ 2>/dev/null | grep -c '探针' ) 个"
echo "    列表里还出现吗：$(curl -s -m 20 http://127.0.0.1:8011/gen/api/outputs | grep -c '探针') 次（应为 0）"

echo
echo "  --- 4.3 恢复探针，再测彻底删除 ---"
mv "$ARC"/*探针* "$PROBE" 2>/dev/null
echo "    恢复后存在：$([ -f "$PROBE" ] && echo 是 || echo 否)"
code=$(curl -s -o /tmp/r.json -w '%{http_code}' -m 30 -X POST http://127.0.0.1:8011/gen/api/delete \
       -H 'Content-Type: application/json' --data-binary '{"name":"_探针_归档删除.docx"}')
echo "    HTTP $code  $(cat /tmp/r.json)"
echo "    文件还在吗：$([ -f "$PROBE" ] && echo '在（不对）' || echo '已删除（对）')"

echo
echo "  --- 4.4 生产目录有没有被误动 ---"
echo "    顶层 .docx：$(ls $OUT/*.docx 2>/dev/null | wc -l) 份"
echo "    _已归档/  ：$(ls $ARC/ 2>/dev/null | wc -l) 个"

echo
echo "================ 5. 静态资源 ================"
echo "  gen_ui.js  含 data-act=archive：$(curl -s -m 20 http://127.0.0.1:8011/gen/static/gen_ui.js | grep -c 'data-act="archive"')"
echo "  gen_ui.js  含 ge-foot        ：$(curl -s -m 20 http://127.0.0.1:8011/gen/static/gen_ui.js | grep -c 'ge-foot')（应为 0）"
echo "  gen_ui.css 含 ge-out-act     ：$(curl -s -m 20 http://127.0.0.1:8011/gen/static/gen_ui.css | grep -c 'ge-out-act')"
echo "  gen_ui.css 含 ge-foot        ：$(curl -s -m 20 http://127.0.0.1:8011/gen/static/gen_ui.css | grep -c 'ge-foot')（应为 0）"
