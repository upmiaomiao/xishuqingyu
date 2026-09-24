#!/usr/bin/env bash
# 只读：GB 3095 两份材料的路径/front matter/过渡期限值原文；以及法典自身块的状态。
set -u
echo "===== 1) 库里所有含 3095 的 md ====="
find /data/fagui_rag/okf_bundles -name "*.md" | grep 3095 | head -10

echo
echo "===== 2) 各自 front matter（前 22 行）====="
for f in $(find /data/fagui_rag/okf_bundles -name "*.md" | grep 3095 | head -10); do
  echo "---------- $f"
  sed -n '1,22p' "$f"
  echo
done

echo
echo "===== 3) 过渡期/阶段 相关原文（每份取 3 处上下文）====="
for f in $(find /data/fagui_rag/okf_bundles -name "*.md" | grep 3095); do
  echo "---------- $f"
  grep -n "过渡\|第一阶段\|第二阶段\|2031\|2030" "$f" | head -8
  echo
done

echo
echo "===== 4) 法典自身块的 status（它必须是现行）====="
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import io, json
c = {}
with io.open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8", errors="replace") as f:
    for line in f:
        if "生态环境法典" not in line:
            continue
        o = json.loads(line)
        if "生态环境法典" in (o.get("source") or ""):
            c[o.get("status") or "(空)"] = c.get(o.get("status") or "(空)", 0) + 1
print("  法典自身块 status 分布：", c)
PY
