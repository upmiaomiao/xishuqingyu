#!/usr/bin/env bash
# 下载两个 .doc 附件，看真身，并检查有无转换工具
set -u
C=/data/fagui_rag/criteria
mkdir -p "$C"
cd "$C"
for u in \
  "https://www.gov.cn/zhengce/zhengceku/2021-01/04/5576531/files/951e99b980fe46b78754f0fa502cac54.doc" \
  "https://www.gov.cn/zhengce/zhengceku/2021-01/04/5576531/files/beec550c77bb450eaf93e2a3baa7a22d.doc" ; do
  f=$(basename "$u")
  python3 - "$u" "$f" <<'PY'
import sys, urllib.request
u, f = sys.argv[1], sys.argv[2]
req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
with urllib.request.urlopen(req, timeout=120) as r:
    raw = r.read()
open(f, "wb").write(raw)
print(f"{f}: {len(raw):,} 字节  头部 {raw[:8]!r}")
PY
done
echo
echo "== 是否其实是 zip/docx =="
for f in *.doc; do
  [ -f "$f" ] || continue
  printf "%s: " "$f"; head -c 4 "$f" | xxd | head -1
done
echo
echo "== 转换工具 =="
for t in soffice libreoffice antiword catdoc pandoc; do
  printf "%-12s %s\n" "$t" "$(command -v $t || echo '（无）')"
done
echo
echo "== python 可用库 =="
python3 -c "
for m in ('docx','olefile','textract','mammoth'):
    try:
        __import__(m); print('  ', m, 'OK')
    except Exception as e:
        print('  ', m, '缺失')
"
ls -la "$C"
