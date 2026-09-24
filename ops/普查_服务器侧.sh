#!/usr/bin/env bash
# 服务器侧验收套件普查：这些脚本本地跑不了（要 retriever 模块 / 要 127.0.0.1:8011），
# 只能在 .10 上用站点的 venv python 跑。逐个记录 rc + 尾部输出。
V=/home/test/fagui_serve/.venv/bin/python
B=/home/test/_验收脚本
export PYTHONPATH=/data/fagui_rag:/data/eia_audit:/home/test/xishu_qingyu_serve:$PYTHONPATH
cd /data/fagui_rag || exit 1

run() {   # run <相对路径> <超时秒>
  local f="$B/$1" t="$2"
  if [ ! -f "$f" ]; then echo "❓ 缺脚本 $1"; return; fi
  local t0=$(date +%s)
  local out
  out=$(timeout "$t" "$V" "$f" 2>&1)
  local rc=$?
  local dt=$(( $(date +%s) - t0 ))
  if [ $rc -eq 0 ]; then echo "✅ 通过 ${dt}s  $1";
  else echo "❌ 失败(rc=$rc) ${dt}s  $1"; echo "$out" | tail -6 | sed 's/^/      /'; fi
}

echo "===================== 检索/语料验收 ====================="
run "质量校验/验收报告语料不淹没.py" 900
run "质量校验/验证环评样本.py" 900
run "质量校验/验证语料上限修法.py" 600
run "质量校验/查重排服务.py" 300
run "质量校验/验收导则问答.py" 900
run "质量校验/验收关键数字.py" 900
run "站点全量测试/查韧性层.py" 600
run "站点全量测试/查代码结构.py" 300

echo
echo "===================== 审核侧 ====================="
run "审核智能体/服务端/查判据.py" 300
run "审核智能体/服务端/查证据.py" 300
run "审核智能体/服务端/查界面契约.py" 600

echo
echo "===================== 生成侧 ====================="
run "报告生成/服务端/自测生成页.py" 1800
run "报告生成/服务端/查嵌入契约.py" 600
run "报告生成/服务端/查生成界面契约.py" 600
run "报告生成/服务端/查生成速度.py" 600
run "报告生成/服务端/查直排来源.py" 600
