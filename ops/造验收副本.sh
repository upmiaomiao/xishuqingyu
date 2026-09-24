#!/bin/bash
# 造一份**内容不同**的临时副本（引擎按 sha1 去重，逐字节相同的副本不会出现在清单里）。
# 只在 %%EOF 之后追加一行 PDF 注释 —— 相当于增量更新文件的尾部，
# 解析器会忽略它，但字节变了 → sha1 变了 → 会出现在清单里。
# 追加完立刻用 pymupdf 打开校验页数与文本，确认没弄坏。
set -e
cd /data/eia_reports
src="1、中节能（临沂）环保能源有限公司第二垃圾焚烧发电项目环境影响报告书.pdf"
dst="_验收副本_临沂.pdf"
cp -f "$src" "$dst"
printf '\n%%%% 验收副本 %s\n' "$(date +%%Y-%%m-%%d_%%H:%%M:%%S)" >> "$dst"
echo "--- 大小 ---"
ls -l "$src" "$dst"
echo "--- sha1 ---"
sha1sum "$src" "$dst"
echo "--- 打开校验 ---"
/home/test/fagui_serve/.venv/bin/python - "$dst" <<'PY'
import sys, fitz
d = fitz.open(sys.argv[1])
print("页数", d.page_count, "| 第14页前40字:", repr(d[13].get_text("text", sort=True)[:40]))
print("是否加密:", d.is_encrypted)
PY
