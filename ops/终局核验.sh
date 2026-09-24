#!/bin/bash
# 终局核验：阶段 0 卫生 + 启动器冻结 + 回滚可用性。
# 「可回滚」不能只靠"备份文件在那儿"，要证明它**内容和基线一致**。
D=/home/test/xishu_qingyu_serve
ARC=/home/test/_重构归档_20260918

echo "############ A. 阶段 0：生产目录卫生 ############"
for sub in frontend xishu_pipeline/static xishu_pipeline; do
  n=$(find "$D/$sub" -maxdepth 1 -type f \( -name '*.bak' -o -name '*.orig' -o -name '*.old' \
        -o -name '*~' -o -name '*.tmp' -o -name '*.pyc' -o -name '*.save' \) 2>/dev/null | wc -l)
  printf '  %-24s 备份/临时文件 %s 个\n' "$sub" "$n"
done
printf '  %-24s __pycache__ %s 个\n' "xishu_pipeline" "$(find "$D" -name __pycache__ -type d 2>/dev/null | wc -l)"
printf '  %-24s .pyc %s 个\n' "全目录" "$(find "$D" -name '*.pyc' 2>/dev/null | wc -l)"

echo
echo "############ B. 冻结的启动器（必须与基线一致）############"
L="$D/launch_xishu_qingyu_qa_8011.sh"
if [ -f "$L" ]; then
  M=$(md5sum "$L" | cut -d' ' -f1)
  printf '  md5 %s\n' "$M"
  if [ "$M" = "fdabd26175e125d4d0ca62ac4abffce1" ]; then
    echo "  √ 与基线 fdabd26175e125d4d0ca62ac4abffce1 一致（未被改动）"
  else
    echo "  × 与基线不一致 —— 启动器被改过！"
  fi
else
  echo "  ! 找不到启动器"
fi

echo
echo "############ C. 回滚素材清单 ############"
ls -1 "$ARC" 2>/dev/null | sed 's/^/  /'
echo
echo "  各阶段备份："
for st in 阶段1前 阶段2a前 阶段2b前 阶段3前; do
  if [ -d "$ARC/$st" ]; then
    printf '    %-10s %s 个文件\n' "$st" "$(ls -1 "$ARC/$st" | wc -l)"
  else
    printf '    %-10s 缺失\n' "$st"
  fi
done

echo
echo "############ D. 回滚可用性验证 ############"
echo "  判据：对基线里每个文件，先看**线上**是否还等于基线。"
echo "        · 相等  -> 本次没动过它，不需要回滚"
echo "        · 不等  -> 动过了，必须在备份里能找到改造前的原件"
echo "  为什么不能只查「备份里有没有这个文件」：没改过的文件当然没有备份，"
echo "  那会把 15 个从未改动的模块误报成「回滚素材缺失」。"
echo "  也不能按文件名后缀硬编码映射 —— audit_routes.py / gen_routes.py 都会命中"
echo "  *routes.py，我第一版就是这么写的，拿错了对比对象、报出 3 个假不一致。"
BASE="$ARC/基线md5_20260918-095425.txt"
if [ -f "$BASE" ]; then
  INDEX=$(mktemp)
  find "$ARC" -type f -exec md5sum {} \; 2>/dev/null | sort > "$INDEX"
  same=0; ok=0; moved=0; bad=0
  while read -r h p; do
    [ -z "$h" ] && continue
    live="$D/$p"
    if [ ! -f "$live" ]; then
      # 不在原位，但可能只是被**移动**了（阶段 0 卫生把测试脚本移出生产静态目录）。
      # 在服务目录内按 md5 反查一次，找到且内容一致就算"移动"而非"丢失"。
      # 注意范围只到 $D：全盘 find /home/test 会扫到大数据目录，实测直接超时。
      hit=$(find "$D" -type f -not -path '*/__pycache__/*' -exec md5sum {} \; 2>/dev/null \
            | grep "^$h " | head -1 | sed 's/^[a-f0-9]*  //')
      if [ -n "$hit" ]; then
        printf '  → %-40s 已移动（内容未变）：%s\n' "$p" "$hit"
        moved=$((moved+1))
      else
        printf '  × %-40s 线上不存在，且全盘找不到内容一致的副本！\n' "$p"
        bad=$((bad+1))
      fi
      continue
    fi
    g=$(md5sum "$live" | cut -d' ' -f1)
    if [ "$g" = "$h" ]; then
      printf '  = %-40s 与基线一致（本次未改动）\n' "$p"
      same=$((same+1))
    else
      hit=$(grep "^$h " "$INDEX" | head -1 | sed 's/^[a-f0-9]*  //')
      if [ -n "$hit" ]; then
        printf '  √ %-40s 已改动，原件在：%s\n' "$p" "${hit#$ARC/}"
        ok=$((ok+1))
      else
        printf '  × %-40s 已改动，但备份里找不到原件！\n' "$p"
        bad=$((bad+1))
      fi
    fi
  done < "$BASE"
  rm -f "$INDEX"
  echo
  echo "  基线共 $((same+ok+moved+bad)) 项：未改动 $same / 已改动且可回滚 $ok / 已移动 $moved / 有问题 $bad"
  if [ "$bad" -eq 0 ]; then
    echo "  √ 所有已改动文件均可从备份复原 —— 回滚路径完整"
  fi
else
  echo "  ! 找不到基线 md5 记录"
fi

echo
echo "############ E. 线上当前状态 ############"
ss -ltnp 2>/dev/null | grep ':8011' | sed 's/^/  /'
printf '  /health：%s\n' "$(curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8011/health)"
