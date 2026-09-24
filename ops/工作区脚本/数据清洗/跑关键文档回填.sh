#!/usr/bin/env bash
# 对业务关键文档执行回填（验收用）
set -u
PY=/data/fagui_rag/.venv_tools/bin/python
T=/tmp/回填清单.json
S=/tmp/stage_probe
R=/tmp/probe_keys.json

run() {
  echo "==================== $1"
  $PY /tmp/语料正文回填.py repair --targets "$T" --stage "$S" --report "$R" --free-search --match "$1" \
    2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated | grep -e "待处理" -e "处理 " -e "新增正文" -e "追加" -e "回填槽位"
}

run "国家危险废物名录"
run "储油库大气污染物排放标准（GB 20950—2020"
run "制糖工业水污染物排放标准（GB 21909-2008"
run "一般工业固体废物贮存和填埋污染控制标准 GB 18599"

echo
echo "==================== 关键数字验收"
python3 /tmp/验收关键数字.py "$S"
