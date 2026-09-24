"""摸清审核引擎：报告目录在哪、接受什么格式、怎么列。

`AUDIT_HOME = /data/eia_audit`（不是 /data/eia_report_gen），
先确认这个目录、报告存放位置、以及 list_reports 认哪些后缀 ——
这决定"上传自己的环评报告"该允许什么格式、文件放哪。
"""
import os
import sys

AUDIT_HOME = os.environ.get("AUDIT_HOME", "/data/eia_audit")
sys.path.insert(0, AUDIT_HOME)

print("=== AUDIT_HOME ===")
print("  ", AUDIT_HOME, "存在" if os.path.isdir(AUDIT_HOME) else "★ 不存在")

print()
print("=== AUDIT_HOME 顶层 ===")
if os.path.isdir(AUDIT_HOME):
    for n in sorted(os.listdir(AUDIT_HOME))[:30]:
        p = os.path.join(AUDIT_HOME, n)
        kind = "dir " if os.path.isdir(p) else "file"
        sz = "" if os.path.isdir(p) else ("%d B" % os.path.getsize(p))
        print("  %s %-46s %s" % (kind, n[:46], sz))

print()
print("=== audit 包 ===")
pk = os.path.join(AUDIT_HOME, "audit")
if os.path.isdir(pk):
    for n in sorted(os.listdir(pk)):
        print("   ", n)
else:
    print("   ★ 没有 audit/ 子目录")

print()
print("=== list_reports / report_dir ===")
try:
    from audit.runner import list_reports, report_dir
    d = report_dir()
    print("  report_dir =", d)
    print("  存在 =", os.path.isdir(d))
    rs = list_reports()
    print("  报告数 =", len(rs))
    for n in rs[:15]:
        print("    ", n)
except Exception as exc:
    import traceback
    print("  ★ 取不到：", repr(exc))
    traceback.print_exc()

print()
print("=== list_reports 认哪些后缀（看源码）===")
try:
    import inspect
    from audit import runner
    src = inspect.getsource(runner.list_reports)
    print(src)
    src2 = inspect.getsource(runner.report_dir)
    print(src2)
except Exception as exc:
    print("  ★ 读源码失败：", repr(exc))

print()
print("=== audit_file 的签名与支持的格式 ===")
try:
    import inspect
    from audit import runner
    print("  audit_file:", inspect.signature(runner.audit_file))
    doc = (runner.audit_file.__doc__ or "").strip()
    if doc:
        print("  说明:", doc[:400])
    # 找解析入口
    for name in ("parse", "extract", "read_report", "load_report"):
        if hasattr(runner, name):
            print("  另有:", name, inspect.signature(getattr(runner, name)))
except Exception as exc:
    print("  ★ 失败：", repr(exc))

print()
print("=== 解析层支持的后缀（grep 整个 audit 包）===")
import re
pat = re.compile(r"\.(pdf|docx|doc|txt|md|wps)\b")
hits = {}
for dirpath, _, names in os.walk(pk):
    if "__pycache__" in dirpath:
        continue
    for n in names:
        if not n.endswith(".py"):
            continue
        p = os.path.join(dirpath, n)
        try:
            text = open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in pat.findall(text):
            hits.setdefault(m, []).append(os.path.relpath(p, AUDIT_HOME))
for ext, files in sorted(hits.items()):
    uniq = sorted(set(files))
    print("  .%-5s 出现在: %s" % (ext, ", ".join(uniq[:4])))

print()
print("=== 磁盘 ===")
os.system("df -h /data | tail -1")
