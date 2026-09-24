#!/bin/bash
# 1) 标准类 md 的 front matter 模板  2) 报告类标题异常全量清单
set -u
OKF=/data/fagui_rag/okf_bundles

echo "===== 1) 一份标准 md 的完整 front matter（GB 16889-2024）====="
f=$(find "$OKF" -path '*16889*' -name '*.md' | head -1)
echo "文件：$f"
sed -n '1,26p' "$f"

echo
echo "===== 2) 环评报告类：front matter title 全量分布（前 25 种）====="
/home/test/fagui_serve/.venv/bin/python - <<'PY'
from pathlib import Path
from collections import Counter
import re, yaml
root = Path("/data/fagui_rag/okf_bundles/环评报告")
FR = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
c = Counter(); empty = 0; bad_files = {}
for md in sorted(root.rglob("*.md")):
    t = md.read_text(encoding="utf-8", errors="replace")
    m = FR.match(t)
    fm = {}
    if m:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            fm = {}
    title = fm.get("title")
    if not isinstance(title, str) or not title.strip():
        empty += 1
        c[f"（空/非字符串：{type(title).__name__}）"] += 1
        bad_files.setdefault("（空）", []).append(md.stem)
        continue
    title = title.strip()
    c[title] += 1
    bad_files.setdefault(title, []).append(md.stem)
print(f"环评报告 md 共 {sum(c.values())} 份；title 为空 {empty} 份")
for t, n in c.most_common(25):
    print(f"  {n:>4}  {t[:70]}")
print("\n重复标题的情况（同一 title 被多份文件用）：")
for t, n in c.most_common(12):
    if n > 1:
        print(f"  「{t[:50]}」×{n}：")
        for s in bad_files[t][:4]:
            print(f"      - {s[:78]}")
PY
