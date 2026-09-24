#!/bin/bash
# 找线上真正的"判据库"目录（名录 JSON 在哪），并跑 C5 专项单测。
set -u
echo "==== 1) /data/eia_report_gen/判据库 里有什么 ===="
ls -l /data/eia_report_gen/判据库 2>/dev/null | head -20

echo
echo "==== 2) 全盘找 分类管理名录2021.json ===="
find / -name '分类管理名录2021.json' -not -path '/proc/*' 2>/dev/null | head

echo
echo "==== 3) criteria.py 里的默认判据目录 ===="
grep -n 'DEFAULT_DIR' /data/eia_audit/audit/criteria.py | head -5

echo
echo "==== 4) 跑 C5 专项单测（用找到的真实判据目录）====="
D=$(find / -name '分类管理名录2021.json' -not -path '/proc/*' 2>/dev/null | head -1)
D=$(dirname "$D")
echo "  判据目录：$D"
cd /home/test && EIA_CRITERIA_DIR="$D" python3 - <<'PY'
import os, sys
sys.path.insert(0, "/data/eia_audit")
from audit.criteria import Criteria
C = Criteria(os.environ["EIA_CRITERIA_DIR"])
print("  名录条目 %d 条" % len(C.catalog))
for q in ("年产5000吨环氧树脂项目 合成材料制造 265 环氧树脂 5000吨/年 环氧氯丙烷 双酚A",
          "年产5000吨环氧树脂项目 环氧树脂 5000吨/年",
          "新建学校项目 建筑面积6000平方米 教学楼 中学"):
    items = C.find_items(q, top=3)
    print("  查询：%s" % q)
    print("    → %s" % [(it["no"], it["category"][:26]) for it in items])
PY
