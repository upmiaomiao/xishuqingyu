#!/bin/bash
# [025] 给问答线的检索结果透传「废止依据」(status_note)。
#
# 根因（2026-09-23 定位）：
#   xishu_pipeline/retrieve.py::normalize_sources() 用**显式白名单**把检索命中透传给前端与提示词，
#   2026-09-22 加 status 时**漏了 status_note**；而 xishu_pipeline/pipeline.py::source_block()
#   第 71-73 行本来就会渲染「时效状态：已废止 —— 依据」。于是：索引里有依据、提示词拿不到，
#   模型只能说"材料未显示废止它的具体法律名称"（甚至会反过来怀疑标注是录入错误）。
#
# 做法：只加一个字段，不动任何判定/排序逻辑。
set -u
F=/home/test/xishu_qingyu_serve/xishu_pipeline/retrieve.py
TS=$(date +%Y%m%d_%H%M%S)
BAK="$F.bak_before_statusnote_$TS"
# 2026-09-23 实测的改前 md5（改前必须逐字节一致，否则说明线上已被别处改过 → 停下来看）
EXPECT="f1906fa7d07f04add11d0eadd8645f7d"

echo "==== 1) 改前核对 ===="
LIVE=$(md5sum "$F" | cut -d' ' -f1)
echo "  线上 md5 : $LIVE"
echo "  期望(改前): $EXPECT"
if [ "$LIVE" != "$EXPECT" ]; then
  echo "  ❌ 不一致：线上这份与预期不同，**先别改** —— 可能已被别处改过，需人工比对"
  exit 3
fi
echo "  ✅ 逐字节一致"
grep -n 'status_note' "$F" || echo "  确认：现在文件里没有 status_note ✅（正是根因）"

echo
echo "==== 2) 备份 ===="
cp -p "$F" "$BAK"
echo "  备份 → $BAK"
echo "  备份 md5: $(md5sum "$BAK" | awk '{print $1}')"

echo
echo "==== 3) 打补丁（在 status 那行后面加一行 status_note）===="
python3 - "$F" <<'PY'
import io, re, sys
p = sys.argv[1]
t = io.open(p, encoding="utf-8").read()
if "status_note" in t:
    print("  已有 status_note，跳过"); raise SystemExit(0)
pat = re.compile(r'^(?P<ind>\s*)"status": hit\.get\("status"\) or "",\s*$', re.M)
m = pat.search(t)
if not m:
    print("  ❌ 没找到锚点行，未改动"); raise SystemExit(2)
ins = '%s"status_note": hit.get("status_note") or "",\n' % m.group("ind")
t2 = t[:m.end() + 1] + ins + t[m.end() + 1:]
io.open(p, "w", encoding="utf-8", newline="\n").write(t2)
print("  ✅ 已在 status 后插入 status_note")
PY
rc=$?
if [ $rc -ne 0 ]; then echo "  补丁未应用（rc=$rc），恢复备份"; cp -p "$BAK" "$F"; exit 1; fi

echo
echo "==== 4) 改后核对 ===="
echo "  线上 md5 : $(md5sum "$F" | awk '{print $1}')"
python3 -c "import ast,io;ast.parse(io.open('$F',encoding='utf-8').read());print('  语法检查 ✅')"
grep -n 'status\|status_note\|doc_type' "$F" | head -8

echo
echo "==== 5) 清 pyc 缓存（否则旧字节码可能被复用）===="
find /home/test/xishu_qingyu_serve/xishu_pipeline/__pycache__ -name 'retrieve.*.pyc' -delete 2>/dev/null
echo "  已清 $(ls /home/test/xishu_qingyu_serve/xishu_pipeline/__pycache__/retrieve.*.pyc 2>/dev/null | wc -l) 个残留"

echo
echo "==== 6) 回滚方法（记下来）===="
echo "  cp -p $BAK $F && bash /home/test/安全重启8011.sh"
