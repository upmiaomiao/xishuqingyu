#!/bin/bash
# 决定性判据：这份草稿的输入是不是模块里的测试样本？
echo "=========== 1. 生成模块里有没有「汪沟镇」==========="
grep -rn '汪沟镇' /data/eia_report_gen/ --include=*.py --include=*.json --include=*.md --include=*.txt 2>/dev/null | head -10 | sed 's/^/  /'
echo "  （空 = 不是样本里的）"

echo
echo "=========== 2. 有没有「20 吨/小时」这种样本串 ==========="
grep -rn '20 吨/小时\|20吨/小时' /data/eia_report_gen/ --include=*.py --include=*.json --include=*.md 2>/dev/null | head -10 | sed 's/^/  /'

echo
echo "=========== 3. 样本文件在哪、内容是什么 ==========="
ls -la /data/eia_report_gen/ 2>/dev/null | sed 's/^/  /'
echo
echo "  --- 找「示例」相关文件 ---"
find /data/eia_report_gen /home/test/xishu_qingyu_serve -iname '*示例*' -o -iname '*sample*' 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=========== 4. 站点模块里的示例文本 ==========="
grep -rn '虚构示例' /home/test/xishu_qingyu_serve/ /data/eia_report_gen/ --include=*.py --include=*.js 2>/dev/null | head -10 | sed 's/^/  /'

echo
echo "=========== 5. 会话状态文件（对话采集会留痕）==========="
find /data/eia_report_gen -iname '*会话*' -o -iname '*session*' -o -iname '*state*' 2>/dev/null | head -20 | sed 's/^/  /'
echo "  --- 找最近 1 小时内改动的 json ---"
find /data/eia_report_gen -name '*.json' -mmin -120 2>/dev/null | head -20 | sed 's/^/  /'

echo
echo "=========== 6. 兰山生物质供热站 是不是样本 ==========="
grep -rn '兰山生物质供热站\|阳光村' /data/eia_report_gen/ /home/test/xishu_qingyu_serve/ --include=*.py --include=*.js --include=*.json 2>/dev/null | head -10 | sed 's/^/  /'
