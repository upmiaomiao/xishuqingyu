#!/bin/bash
# 阶段 2a 验证：部署 app.css + 新 index.html，证明样式零变化
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918/阶段2a前
FR=$D/frontend
B=http://127.0.0.1:8011

echo "=========== 2a.1 重启 ==========="
bash /home/test/安全重启8011.sh 2>&1 | sed 's/^/  /'

echo
echo "=========== 2a.2 静态资源可取 ==========="
printf '  /static/app.css -> %s  %s  %s 字节\n' \
  "$(curl -s -o /tmp/a.css -w '%{http_code}' -m 15 $B/static/app.css)" \
  "$(curl -s -o /dev/null -w '%{content_type}' -m 15 $B/static/app.css)" \
  "$(stat -c%s /tmp/a.css)"
echo "  与本地 app.css 是否逐字节一致：$(md5sum /tmp/a.css | cut -d' ' -f1)"
echo "  本地：                           $(md5sum $FR/app.css | cut -d' ' -f1)"

echo
echo "=========== 2a.3 首页不再内联 ==========="
curl -s -m 20 $B/ -o /tmp/idx.html
echo "  字节数：$(stat -c%s /tmp/idx.html)（拆分前 41132）"
echo "  含 <style>       ：$(grep -c '<style' /tmp/idx.html) 次（应为 0）"
echo "  含 app.css 链接  ：$(grep -c 'href="/static/app.css"' /tmp/idx.html) 次（应为 1）"
echo "  <link> 在 </head> 之前：$(awk '/app\.css/{l=NR} /<\/head>/{h=NR} END{print (l<h)?"是":"否"}' /tmp/idx.html)"

echo
echo "=========== 2a.4 ★ 核心：样式与原内联 CSS 是否等价 ==========="
# 从备份的旧 index.html 里抽出原来的内联 CSS
python3 - <<'PY'
import io, re, sys
old = io.open("/home/test/_重构归档_20260918/阶段2a前/index.html", encoding="utf-8").read()
blocks = re.findall(r"<style[^>]*>(.*?)</style>", old, re.S)
orig_css = blocks[0] + "\n" + blocks[1]
new_css = io.open("/home/test/xishu_qingyu_serve/frontend/app.css", encoding="utf-8").read()

def strip_comments(s):
    return re.sub(r"/\*.*?\*/", "", s, flags=re.S)

def norm(s):
    return re.sub(r"\s+", "", s)

a, b = norm(strip_comments(orig_css)), norm(strip_comments(new_css))
print("  原内联 CSS  去注释去空白：%d 字符" % len(a))
print("  新 app.css  去注释去空白：%d 字符" % len(b))
if a == b:
    print("  ★★★ 逐字符完全一致 —— 样式零变化 ★★★")
else:
    k = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), min(len(a), len(b)))
    print("  ✗ 不一致！首个差异在第 %d 字符" % k)
    print("    原：%r" % a[max(0, k-40):k+40])
    print("    新：%r" % b[max(0, k-40):k+40])
    sys.exit(1)
# 规则数
print("  规则块数：原 %d / 新 %d" % (len(re.findall(r"\{", strip_comments(orig_css))),
                                    len(re.findall(r"\{", strip_comments(new_css)))))
PY

echo
echo "=========== 2a.5 <script> 未动 ==========="
python3 - <<'PY'
import io, re
old = io.open("/home/test/_重构归档_20260918/阶段2a前/index.html", encoding="utf-8").read()
new = io.open("/tmp/idx.html", encoding="utf-8").read()
jo = re.search(r"<script[^>]*>(.*?)</script>", old, re.S).group(1)
jn = re.search(r"<script[^>]*>(.*?)</script>", new, re.S).group(1)
print("  <script> 内容一致：%s" % ("√" if jo == jn else "✗"))
io_, in_ = sorted(re.findall(r'id="([^"]+)"', old)), sorted(re.findall(r'id="([^"]+)"', new))
print("  id 集合一致：%s（原 %d 个 / 新 %d 个）" % ("√" if io_ == in_ else "✗", len(io_), len(in_)))
if jo != jn or io_ != in_:
    raise SystemExit(1)
PY

echo
echo "=========== 2a.6 全部通路 ==========="
for p in / /gen /audit /health /kg/stats /audit/api/reports /gen/api/outputs /static/app.css; do
  printf '  %-22s %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 20 $B$p)"
done
echo "  生成页列表份数：$(curl -s -m 20 $B/gen/api/outputs | grep -o '"name"' | wc -l)"
