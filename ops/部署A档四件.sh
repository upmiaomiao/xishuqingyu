#!/bin/bash
# A 档四件部署：C10-③（decide 单位折算）、C10-①（criteria 亩系数）、A2（items_extra 标准现行性）、
# C9（narrate 措施闸门 + 无措施事实不写该节）。
#
# 纪律：逐个文件核对「改前 md5」→ 备份 → 覆盖 → 语法/JSON 校验 → 打印回滚命令。
# 任何一个环节不对就**停下来**，不硬着头皮往下走。
set -u
STAGE=/home/test/_A档_待部署
TS=$(date +%Y%m%d_%H%M%S)
BAD=0

echo "==== 0) 待部署文件 ===="
ls -l "$STAGE" || exit 1

# 名称|目标路径|改前 md5（服务器上的现状；"无" 表示新增文件）
ROWS="
criteria.py|/data/eia_audit/audit/criteria.py|3cdc58b3c2cd0804f48f227f95a19f50
items_extra.py|/data/eia_audit/audit/items_extra.py|ce6db16b63de987d64b1ea3d668dd4a0
decide.py|/data/eia_report_gen/gen/decide.py|9ddf4aa7e74069dfe3a7e57e4106d4e1
narrate.py|/data/eia_report_gen/gen/narrate.py|7f00c1c8086d08119a09cb462ab87b09
标准现行性.json|/data/fagui_rag/criteria/标准现行性.json|无
"

echo
echo "==== 1) 改前核对（逐字节）===="
echo "$ROWS" | while IFS='|' read -r name dst want; do
  [ -z "${name:-}" ] && continue
  src="$STAGE/$name"
  [ -f "$src" ] || { echo "  ❌ 暂存缺文件：$src"; exit 3; }
  if [ -f "$dst" ]; then
    live=$(md5sum "$dst" | cut -d' ' -f1)
    if [ "$want" = "无" ]; then
      echo "  ⚠️  $dst 已存在（预期是新增文件）live=$live —— 停下来人工看"
      exit 4
    fi
    if [ "$live" != "$want" ]; then
      echo "  ❌ $dst 线上 md5=$live ≠ 期望(改前)=$want —— 说明已被别处改过，**先别部署**"
      exit 5
    fi
    echo "  ✅ $name 改前一致（$live）"
  else
    [ "$want" = "无" ] || { echo "  ❌ $dst 不存在，但期望有改前版本 $want"; exit 6; }
    echo "  ✅ $name 是新文件（$dst 原不存在）"
  fi
done
rc=$?
[ $rc -ne 0 ] && { echo "改前核对未通过（rc=$rc），未做任何改动"; exit $rc; }

echo
echo "==== 2) 备份 + 覆盖 ===="
echo "$ROWS" | while IFS='|' read -r name dst want; do
  [ -z "${name:-}" ] && continue
  src="$STAGE/$name"
  if [ -f "$dst" ]; then
    cp -p "$dst" "$dst.bak_before_A_$TS"
    echo "  备份 → $dst.bak_before_A_$TS"
  fi
  cp -p "$src" "$dst"
  case "$name" in
    *.py)
      if python3 -c "import ast,io,sys;ast.parse(io.open(sys.argv[1],encoding='utf-8').read())" "$dst"; then
        echo "  ✅ $name 部署完成（语法 OK）  md5=$(md5sum "$dst" | cut -d' ' -f1)"
      else
        echo "  ❌ $name 语法错误，已从备份恢复"
        [ -f "$dst.bak_before_A_$TS" ] && cp -p "$dst.bak_before_A_$TS" "$dst"
        exit 7
      fi
      ;;
    *.json)
      if python3 -m json.tool "$dst" > /dev/null; then
        echo "  ✅ $name 部署完成（JSON OK）  条数=$(python3 -c "import json,io,sys;print(len(json.load(io.open(sys.argv[1],encoding='utf-8')).get('条目') or []))" "$dst")"
      else
        echo "  ❌ $name JSON 非法"; exit 8
      fi
      ;;
  esac
done
rc2=$?
[ $rc2 -ne 0 ] && { echo "❌ 部署过程中出错（rc=$rc2）—— 按第 4 节的命令回滚，然后告诉我"; exit $rc2; }

echo
echo "==== 3) 清 pyc（避免旧字节码）===="
find /data/eia_audit/audit/__pycache__ -name 'criteria.*.pyc' -o -name 'items_extra.*.pyc' 2>/dev/null | while read -r f; do rm -f "$f"; echo "  删除 $f"; done
find /data/eia_report_gen/gen/__pycache__ -name 'decide.*.pyc' -o -name 'narrate.*.pyc' 2>/dev/null | while read -r f; do rm -f "$f"; echo "  删除 $f"; done

echo
echo "==== 4) 回滚方法（记下来）===="
echo "$ROWS" | while IFS='|' read -r name dst want; do
  [ -z "${name:-}" ] && continue
  echo "  cp -p $dst.bak_before_A_$TS $dst"
done
echo "  bash /home/test/安全重启8011.sh"
echo
echo "下一步：bash /home/test/安全重启8011.sh"
