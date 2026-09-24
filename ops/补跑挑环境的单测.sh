#!/bin/bash
# 补跑两支"挑环境"的单测（不是回归，是路径/依赖问题）：
#   · 单测_防编造.py 需要 fitz（用站点 venv）+ 一份真实报告 PDF（按它写死的相对路径放好）
#   · 单测_审核界面.py 按 <根>/审核智能体/服务端/static/audit_ui.js 找前端源码 → 按真实结构摆好
set -u
export EIA_CRITERIA_DIR=/data/fagui_rag/criteria
export EIA_ENGINE_DIR=/data/eia_audit
export PYTHONPATH=/data/eia_audit:/data/eia_report_gen
export AUDIT_HOME=/data/eia_audit
VENV=/home/test/fagui_serve/.venv/bin/python
# 界面单测要 `服务端/audit.html` + `服务端/static/*.js|css` —— 而站点实际是
# html 在 frontend/、js/css 在 xishu_pipeline/static/。按单测期望的结构拼一个出来。
HTML=/home/test/xishu_qingyu_serve/frontend
STATIC=/home/test/xishu_qingyu_serve/xishu_pipeline/static
ROOT=/home/test/最终回归/审核智能体
mkdir -p "$ROOT/单测" "$ROOT/服务端" "/home/test/环评报告/环评报告"
cp -f /home/test/A档单测/单测_审核界面.py "$ROOT/单测/"
cp -f /home/test/A档单测/单测_防编造.py "$ROOT/单测/"
cp -f "$HTML"/*.html "$ROOT/服务端/"
ln -sfn "$STATIC" "$ROOT/服务端/static"
echo "服务端内容：$(ls "$ROOT/服务端" | tr '\n' ' ')｜static：$(ls "$ROOT/服务端/static" | tr '\n' ' ')"
[ -f "/home/test/环评报告/环评报告/环评报告/1、环评报告.pdf" ] || {
  mkdir -p "/home/test/环评报告/环评报告/环评报告"
  ln -sfn "/data/eia_reports/1、环评报告.pdf" "/home/test/环评报告/环评报告/环评报告/1、环评报告.pdf"
  echo "已把真实报告软链到单测期望的路径"
}

echo
echo "================ 单测_防编造.py（站点 venv，有 fitz）"
cd "$ROOT/单测" && "$VENV" 单测_防编造.py 2>&1 | tail -4

echo
echo "================ 单测_审核界面.py（按真实目录结构）"
cd "$ROOT/单测" && python3 单测_审核界面.py 2>&1 | tail -4
