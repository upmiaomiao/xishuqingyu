#!/usr/bin/env bash
# 批次一：对"缺口 >= 1500 字"的文档做正文回填，写入暂存 bundle 树。
set -u
PY=/data/fagui_rag/.venv_tools/bin/python
BUNDLE=/data/fagui_rag/okf_bundles
STAGE=/data/fagui_rag/okf_bundles_stage

# 暂存树 = 线上 bundle 的完整副本，再把修好的文件覆盖进去（保证索引完整）
if [[ ! -d "$STAGE" ]]; then
  echo "复制 bundle → 暂存树…"
  cp -a "$BUNDLE" "$STAGE"
fi

$PY /tmp/语料正文回填.py repair \
  --targets /tmp/回填清单.json \
  --stage "$STAGE" \
  --report /tmp/repair_batch1.json \
  --min-gap 1500 \
  --free-search \
  2>&1 | grep -v -e "MuPDF error" -e pymupdf_layout -e deprecated | tail -20

echo
echo "==================== 补回率与重复检查"
python3 /tmp/算补回率.py /tmp/回填清单.json /tmp/repair_batch1.json
