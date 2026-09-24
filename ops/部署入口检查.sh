#!/usr/bin/env bash
# 把改后的「入口检查」换成 /data/eia_audit/check_entry.py（先备份，再替换，再跑）
SRC=/home/test/查入口_新版.py
DST=/data/eia_audit/check_entry.py
BAK=/home/test/_重构归档_20260919/入口检查_改前
mkdir -p "$BAK"

echo "===== ① 备份现有 ====="
STAMP=$(date +%Y%m%d_%H%M%S)
cp -p "$DST" "$BAK/check_entry.py.$STAMP"
if cmp -s "$BAK/check_entry.py.$STAMP" "$DST"; then echo "备份校验一致：$BAK/check_entry.py.$STAMP"; else echo "！备份校验失败，停止"; exit 1; fi

echo "===== ② 语法预检（在临时位置编译，不覆盖线上）====="
V=/home/test/fagui_serve/.venv/bin/python
if ! "$V" -m py_compile "$SRC"; then echo "！语法不过，停止"; exit 1; fi
echo "语法 OK"

echo "===== ③ 替换 ====="
cp "$SRC" "$DST"
ls -la "$DST"
"$V" - <<'PY'
import hashlib, pathlib
p = pathlib.Path("/data/eia_audit/check_entry.py")
print("线上新文件 md5", hashlib.md5(p.read_bytes()).hexdigest(), p.stat().st_size, "字节")
PY

echo "===== ④ 跑检查 ====="
cd /data/eia_audit || exit 1
"$V" check_entry.py 2>&1 | tail -32
