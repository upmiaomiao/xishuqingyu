#!/bin/bash
# 线上前端的真实构成 —— 判断到底跑的是"单体版"还是"模块化版"
D=/home/test/xishu_qingyu_serve/frontend
echo "=============== 线上 frontend 目录 ==============="
ls -la "$D"
echo
echo "=============== js 子目录 ==============="
ls -la "$D/js" 2>/dev/null || echo "（没有 js 目录！）"
echo
echo "=============== index.html 大小 / 行数 ==============="
wc -c -l "$D/index.html"
echo
echo "=============== 最长行 ==============="
awk '{ if (length($0) > m) { m = length($0); n = NR } } END { print "  第 " n " 行，" m " 字符" }' "$D/index.html"
echo
echo "=============== 外部引用（href/src）==============="
grep -o -E '(href|src)="[^"]+"' "$D/index.html" | sort -u
echo
echo "=============== script 标签原样 ==============="
grep -o -E '<script[^>]*>' "$D/index.html"
echo
echo "=============== 内联 style / script 有多少字符 ==============="
python3 - <<'PY'
import re, pathlib
h = pathlib.Path("/home/test/xishu_qingyu_serve/frontend/index.html").read_text(encoding="utf-8")
for name in ("style", "script"):
    for m in re.finditer(r"<%s[^>]*>(.*?)</%s>" % (name, name), h, re.S):
        seg = m.group(1)
        print("  <%s>  %d 字符 / %d 行" % (name, len(seg), seg.count("\n") + 1))
print("  文件总长：%d 字符" % len(h))
print("  含 import：%s" % (re.findall(r"^\s*import .*$", h, re.M)[:5] or "无"))
PY
echo
echo "=============== app.css 存在吗 ==============="
ls -la "$D/app.css" 2>/dev/null || echo "  线上没有 app.css"
echo
echo "=============== /static/app.css 能取到吗 ==============="
curl -s -o /dev/null -w "  HTTP %{http_code}  %{size_download} 字节\n" http://127.0.0.1:8011/static/app.css
echo "=============== /static/js/main.js 能取到吗 ==============="
curl -s -o /dev/null -w "  HTTP %{http_code}  %{size_download} 字节\n" http://127.0.0.1:8011/static/js/main.js
