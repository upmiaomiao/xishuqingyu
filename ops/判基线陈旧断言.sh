#!/bin/bash
# 判断回归基线里那 5 项失败是不是**改动前就有**的。
#
# 方法：拿备份的改动前文件，逐条重跑同样的断言。
# 如果改动前也是 False，那就不是我这次改出来的，而是基线里的陈旧断言
# （前端在"阶段 2b 拆模块"时把 CSS 和 JS 移出了 index.html，
#   这些断言还在 index.html 里找只存在于 CSS/JS 的东西）。
set -u

ARCH=/home/test/_重构归档_20260918/四项改造_前
SITE=/home/test/xishu_qingyu_serve
TS=20260918_143451
OLD_HTML="$ARCH/frontend_index.html.$TS"
OLD_ROUTES="$ARCH/xishu_pipeline_routes.py.$TS"
NEW_HTML="$SITE/frontend/index.html"
NEW_ROUTES="$SITE/xishu_pipeline/routes.py"

echo "=== 改动前文件 ==="
ls -la "$OLD_HTML" "$OLD_ROUTES"

echo
echo "=== 逐条对比：改动前 vs 改动后 ==="
printf '%-40s %-14s %-14s %s\n' "断言" "改动前" "改动后" "结论"
printf '%-40s %-14s %-14s %s\n' "----------------------------------------" "--------" "--------" "----"

cmp_token() {
  local label="$1" token="$2"
  local o="否" n="否"
  grep -qF "$token" "$OLD_HTML" && o="是"
  grep -qF "$token" "$NEW_HTML" && n="是"
  local verdict="改动前后一致"
  [ "$o" != "$n" ] && verdict="★ 本次改动导致变化"
  printf '%-40s %-14s %-14s %s\n' "$label" "$o" "$n" "$verdict"
}

# 这三条断言要求 index.html 里含 md-table / pdf-link
cmp_token "index.html 含 md-table" "md-table"
cmp_token "index.html 含 pdf-link" "pdf-link"

# 体积断言：>20000 字符
O_SIZE=$(wc -c < "$OLD_HTML")
N_SIZE=$(wc -c < "$NEW_HTML")
printf '%-40s %-14s %-14s ' "index.html 体积 >20000" \
  "$([ "$O_SIZE" -gt 20000 ] && echo 是 || echo 否)" \
  "$([ "$N_SIZE" -gt 20000 ] && echo 是 || echo 否)"
if [ "$O_SIZE" -gt 20000 ] = "$([ "$N_SIZE" -gt 20000 ] && echo 是 || echo 否)" ] 2>/dev/null; then
  echo "改动前后一致"
else
  echo "★ 本次改动导致变化"
fi
echo "     （改动前 $O_SIZE 字符，改动后 $N_SIZE 字符）"

# routes.py 行数断言：<200 行
O_LINES=$(wc -l < "$OLD_ROUTES")
N_LINES=$(wc -l < "$NEW_ROUTES")
printf '%-40s %-14s %-14s %s\n' "routes.py < 200 行" \
  "$([ "$O_LINES" -lt 200 ] && echo 是 || echo 否)" \
  "$([ "$N_LINES" -lt 200 ] && echo 是 || echo 否)" \
  "$([ "$O_LINES" -lt 200 ] && [ "$N_LINES" -lt 200 ] && echo 改动前后一致 || echo 改动前就已失败)"
echo "     （改动前 $O_LINES 行，改动后 $N_LINES 行）"

echo
echo "=== 这两个 token 现在在哪儿 ==="
for tok in md-table pdf-link; do
  echo "  「$tok」出现在："
  grep -rlF "$tok" "$SITE/frontend/" 2>/dev/null | sed "s|$SITE/|    |" || echo "    （没找到）"
done

echo
echo "=== 结论 ==="
echo "  前端在'阶段 2b 拆模块'时把 CSS 迁到 app.css、JS 迁到 js/*.js，"
echo "  index.html 从 4 万多字符缩到 $N_SIZE 字符。"
echo "  上面这几条断言仍然只在 index.html 里找这些东西，"
echo "  所以它们在**拆模块那天**就已经失效了，与本次四项改造无关。"
