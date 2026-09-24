#!/usr/bin/env bash
# 只读：把《生态环境法典》末条（施行与废止清单）原文打出来，并列出 okf_bundles 里这些法律的现状。
set -u
F="/data/fagui_rag/okf_bundles/生态环境法律法规/法律/法律_43/中华人民共和国生态环境法典/中华人民共和国生态环境法典.md"

echo "===== 1) 法典第1242条附近原文 ====="
grep -n "第一千二百四十二条" "$F" | head -3
awk '/第一千二百四十二条/{f=1} f{print; c++} c>14{exit}' "$F"

echo
echo "===== 2) 被废法律在 okf_bundles 里的分册与当前 status ====="
for n in "固体废物污染环境防治法" "环境影响评价法" "海洋环境保护法" "水污染防治法" "大气污染防治法" \
         "环境噪声污染防治法" "土壤污染防治法" "放射性污染防治法" "清洁生产促进法" "循环经济促进法" \
         "环境保护法" "长江保护法" "黄河保护法" "可再生能源法" "节约能源法"; do
  hit=$(find /data/fagui_rag/okf_bundles -type d -name "*${n}*" 2>/dev/null | head -1)
  if [ -z "$hit" ]; then
    echo "  （库里没有）$n"
    continue
  fi
  md=$(find "$hit" -maxdepth 1 -name "*.md" | head -1)
  st=$(grep -m1 '^status:' "$md" 2>/dev/null | tr -d '\r')
  echo "  $n  →  $st    ($md)"
done

echo
echo "===== 3) 索引里这些法律『自身块』的 status 分布 ====="
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import io, json, re
CH = "/data/fagui_rag/index/chunks.jsonl"
WANT = ["固体废物污染环境防治法", "环境影响评价法", "海洋环境保护法", "水污染防治法",
        "大气污染防治法", "环境噪声污染防治法", "土壤污染防治法", "放射性污染防治法",
        "清洁生产促进法", "循环经济促进法", "中华人民共和国环境保护法", "长江保护法",
        "黄河保护法", "GB 3095—2012", "GB 3095—2026"]
cnt = {w: {} for w in WANT}
with io.open(CH, encoding="utf-8", errors="replace") as f:
    for line in f:
        try:
            o = json.loads(line)
        except Exception:
            continue
        src = o.get("source") or ""
        st = o.get("status") or "(空)"
        for w in WANT:
            if w in src:
                cnt[w][st] = cnt[w].get(st, 0) + 1
for w in WANT:
    tot = sum(cnt[w].values())
    print("  %-28s 自身块 %5d   %s" % (w, tot, dict(sorted(cnt[w].items(), key=lambda x: -x[1])) or "—"))
PY
