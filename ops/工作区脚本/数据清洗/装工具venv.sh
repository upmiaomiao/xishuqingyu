#!/usr/bin/env bash
# 在 .10 上建一个独立的工具 venv（不碰服务 venv），装 PyMuPDF。
set -euo pipefail
VENV=/data/fagui_rag/.venv_tools
if [[ ! -x "$VENV/bin/python" ]]; then
  python3 -m venv "$VENV"
fi
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q pymupdf
"$VENV/bin/python" -c "import fitz; print('PyMuPDF', fitz.__version__ if hasattr(fitz,'__version__') else 'ok')"
echo "venv: $VENV"
