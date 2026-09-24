#!/bin/bash
# 追加两份新标准到 index_v3 → index_v3b（增量：只嵌新块的向量）
set -e
PY=/home/test/fagui_serve/.venv/bin/python
echo "===== 语料里确认这两份 ====="
ls -l "/data/fagui_rag/okf_bundles/生态环境标准规范/国家排放标准/生活垃圾焚烧污染控制标准 GB 18485-2014/"
ls -l "/data/fagui_rag/okf_bundles/生态环境标准规范/国家排放标准/危险废物焚烧污染控制标准 GB 18484-2020/"
echo
echo "===== front matter 能否解析（yaml）====="
"$PY" - <<'PY'
import re, yaml
from pathlib import Path
FR = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
root = Path("/data/fagui_rag/okf_bundles/生态环境标准规范/国家排放标准")
for p in sorted(root.rglob("*.md")):
    fm = yaml.safe_load(FR.match(p.read_text(encoding="utf-8")).group(1)) or {}
    print(f"  {p.name}")
    print(f"    title={fm.get('title')!r} type={fm.get('type')!r} "
          f"standard_id={fm.get('standard_id')!r} status={fm.get('status')!r} "
          f"region={fm.get('region')!r}")
PY
echo
echo "===== 增量追加（dry-run）====="
"$PY" /home/test/建索引v3.py --dry-run --src /data/fagui_rag/index_v3 --dst /data/fagui_rag/index_v3b
