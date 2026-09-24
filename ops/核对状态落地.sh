#!/usr/bin/env bash
# 核对：状态改写落地了吗（看 11 份目标文件的 status 行 + 备份目录 + 通用探测是否清空）
set -u
echo "===== 1) 备份目录 ====="
ls -l /home/test/_重构归档_20260922/第二批_前/ 2>/dev/null | head -30
echo "  份数：$(ls /home/test/_重构归档_20260922/第二批_前/ 2>/dev/null | wc -l)"

echo
echo "===== 2) 目标文件的 status 行（应当全是 已废止）====="
/home/test/fagui_serve/.venv/bin/python - <<'PY'
import re, pathlib
B = pathlib.Path("/data/fagui_rag/okf_bundles")
FM = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
names = ["中华人民共和国环境保护法", "中华人民共和国环境影响评价法", "中华人民共和国海洋环境保护法",
         "中华人民共和国大气污染防治法", "中华人民共和国水污染防治法", "中华人民共和国土壤污染防治法",
         "中华人民共和国固体废物污染环境防治法", "中华人民共和国噪声污染防治法",
         "中华人民共和国清洁生产促进法", "GB 3095—2012", "HJ 633—2012", "HJ 663—2013"]
for n in names:
    got = []
    for p in B.rglob("*.md"):
        rel = p.relative_to(B).as_posix()
        if n not in rel or "_归档" in rel:
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        m = FM.match(t)
        st = re.search(r"^status:[ \t]*(.*)$", m.group(1), re.M) if m else None
        note = re.search(r"^status_note:[ \t]*(.*)$", m.group(1), re.M) if m else None
        got.append((st.group(1).strip() if st else "(无)", bool(note), rel.split("/")[-1][:46]))
    for st, has_note, short in got:
        print(f"  {st:<6} note={'有' if has_note else '无'}  {short}")
    if not got:
        print(f"  （库中没有）{n}")
PY
