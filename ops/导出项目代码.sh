#!/bin/bash
# 把"属于本项目的前后端代码"打成一个 tar.gz 供下载入 git。
# 排除：venv、__pycache__、索引、语料、审核/生成结果、缓存、日志、pid、各类 .bak —— 只带代码与配置。
# 用法：bash /home/test/导出项目代码.sh
set -u
cd / || exit 1
OUT=/home/test/_导出代码/xishuqingyu_code.tar.gz
mkdir -p /home/test/_导出代码
LIST=/home/test/_导出代码/文件清单.txt
: > "$LIST"

# 用绝对路径判断是否存在，写进清单时去掉开头的 /（tar 以 / 为工作目录）
add() {
  if [ -e "$1" ]; then
    echo "${1#/}" >> "$LIST"
  else
    echo "  ⚠️ 缺：$1" >&2
  fi
}

# 1) 8011 站点（前端 + xishu_pipeline + 前端测试 + 启动脚本 + 知识图谱数据）
add /home/test/xishu_qingyu_serve/frontend
add /home/test/xishu_qingyu_serve/xishu_pipeline
add /home/test/xishu_qingyu_serve/tests
add /home/test/xishu_qingyu_serve/kg_data
for f in /home/test/xishu_qingyu_serve/launch_*.sh; do add "$f"; done

# 2) 法规问答代理 + 启动脚本
for f in /home/test/fagui_serve/fagui_rag_proxy.py /home/test/fagui_serve/launch_fagui_v3.sh \
         /home/test/fagui_serve/start_fagui_v3.sh; do add "$f"; done

# 3) 两个引擎 + 判据目录
add /data/eia_audit/audit
add /data/eia_report_gen/gen
add /data/eia_report_gen/单测
add /data/eia_report_gen/样例
add /data/eia_report_gen/判据库
add /data/fagui_rag/criteria

# 4) 引擎根级脚本
for f in /data/eia_audit/*.py /data/eia_audit/*.sh /data/eia_report_gen/*.py \
         /data/fagui_rag/*.py /data/fagui_rag/*.sh; do [ -f "$f" ] && add "$f"; done

# 5) /home/test 下的运维与测试脚本（这一路的部署/勘察/验收脚本）
find /home/test -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) | sed 's#^/##' >> "$LIST"
sort -u -o "$LIST" "$LIST"

tar --exclude='__pycache__' --exclude='*.pyc' --exclude='.venv*' --exclude='node_modules' \
    --exclude='*.log' --exclude='*.pid' --exclude='_cache' --exclude='_cache_narr' \
    --exclude='_审核结果' --exclude='_生成结果' --exclude='index' --exclude='index.bak*' \
    --exclude='*.bak_before_*' --exclude='*.bak_p[0-9]_*' --exclude='okf_bundles*' \
    --exclude='eia_reports_raw' --exclude='guides_pdf' --exclude='_backup_标题修正_*' \
    --exclude='_staging' --exclude='*.tar.gz' \
    -czf "$OUT" -T "$LIST" 2>/dev/null

echo "==== 打包结果 ===="
ls -l "$OUT"
echo "清单条目：$(wc -l < "$LIST")　包内文件：$(tar -tzf "$OUT" | wc -l)"
echo "==== 分布（按前两级目录）===="
tar -tzf "$OUT" | sed 's#^\./##' | awk -F/ 'NF>2{print $1"/"$2"/"$3} NF==2{print $1"/"$2} NF==1{print "(根)"}' \
  | sort | uniq -c | sort -rn | head -24
echo "==== 安全自查：包里有没有 .env / 密钥 ===="
tar -tzf "$OUT" | grep -Ei '\.env|secret|token|\.pem|id_rsa|credential' | head -10 \
  || echo "  ✅ 未发现 .env 等敏感文件名"
