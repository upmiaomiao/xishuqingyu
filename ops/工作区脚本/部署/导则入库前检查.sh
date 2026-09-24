#!/usr/bin/env bash
# 入库前检查 + 备份（导则正文语料）
set -u
R=/data/fagui_rag
CORPUS="环评导则"
MD_DIR="$R/okf_bundles/$CORPUS"
PDF_DIR=/data/fagui_pdf/$CORPUS

echo "==== 1) 新语料文件数"
echo "md : $(find "$MD_DIR" -name '*.md' | wc -l)"
echo "pdf: $(find "$PDF_DIR" -name '*.pdf' | wc -l)"
du -sh "$MD_DIR" "$PDF_DIR"

echo
echo "==== 2) frontmatter 字段与 /doc 映射校验"
F="$MD_DIR/HJ 2.1-2016 建设项目环境影响评价技术导则 总纲.md"
echo "--- 前 30 行 ---"
head -30 "$F"
echo "--- 是否含 source_path ---"
grep -c '^source_path:' "$F"
echo "--- /doc 需要的 PDF 路径是否真实存在 ---"
SRC=$(grep '^source_path:' "$F" | head -1 | sed 's/^source_path: *//')
echo "source_path = $SRC"
TGT="/data/fagui_pdf/${SRC%.md}.pdf"
if [ -f "$TGT" ]; then echo "OK  $TGT  ($(stat -c %s "$TGT") 字节)"; else echo "MISSING  $TGT"; fi

echo
echo "==== 3) 正文抽样（跳过 frontmatter，取 900 字）"
awk 'BEGIN{n=0} /^---$/{n++; next} n>=2{print}' "$F" | head -c 900
echo
echo
echo "==== 4) 是否残留页眉页脚噪声（含 HJ 2.1-2016 的行数 vs 总行数）"
echo "lines_total: $(wc -l < "$F")"
echo "lines_with_sid: $(grep -c 'HJ 2.1-2016' "$F")"

echo
echo "==== 5) 备份 index 与 okf_bundles ===="
TS=bak_before_guides_20260916
if [ -d "$R/index.$TS" ]; then echo "已存在 $R/index.$TS，跳过"; else cp -a "$R/index" "$R/index.$TS" && echo "已备份 $R/index.$TS"; fi
if [ -d "$R/okf_bundles.$TS" ]; then echo "已存在 $R/okf_bundles.$TS，跳过"; else cp -a "$R/okf_bundles" "$R/okf_bundles.$TS" && echo "已备份 $R/okf_bundles.$TS"; fi
du -sh "$R/index.$TS" "$R/okf_bundles.$TS"
df -h /data | tail -1
