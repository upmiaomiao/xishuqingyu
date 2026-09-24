"""确认上传所需的前置条件，并查看审核报告目录现状。"""
import os
import shutil
import sys

print("=== 1. python-multipart（FastAPI 收表单/文件必需）===")
try:
    import multipart
    print("  OK  multipart", getattr(multipart, "__version__", "?"))
except ImportError as exc:
    print("  ★ 缺失：", exc)
    print("     → 没有它，用 UploadFile 的端点会直接 500。需要换一种收文件的方式。")

print()
print("=== 2. fastapi 能不能导入 UploadFile / File ===")
try:
    from fastapi import File, UploadFile
    print("  OK  UploadFile / File 可用")
except Exception as exc:
    print("  ★ 失败：", repr(exc))

print()
print("=== 3. starlette 版本（multipart 解析在它里面）===")
try:
    import starlette
    print("  starlette", starlette.__version__)
except Exception as exc:
    print("  ★ ", exc)

print()
print("=== 4. 审核报告目录现状 ===")
sys.path.insert(0, "/data/eia_audit")
try:
    from audit.runner import list_reports, report_dir
    d = report_dir()
    print("  report_dir =", d)
    names = sorted(f for f in os.listdir(d) if f.lower().endswith(".pdf"))
    print("  目录里 .pdf 共 %d 个：" % len(names))
    for n in names:
        print("    %8.1f MB  %s" % (os.path.getsize(os.path.join(d, n)) / 1048576, n))
    uniq = list_reports()
    print("  list_reports() 去重后 %d 个" % len(uniq))
except Exception as exc:
    import traceback
    print("  ★ 失败：", repr(exc))
    traceback.print_exc()

print()
print("=== 5. 可写性 + 磁盘 ===")
d = "/data/eia_reports"
print("  目录可写 =", os.access(d, os.W_OK))
os.system("df -h /data | tail -1")

print()
print("=== 6. python-multipart 装不装得上（看有没有网/源）===")
print("  pip 位置:", shutil.which("pip") or "(venv 里)")
try:
    import importlib.metadata as md
    for pkg in ("python-multipart", "multipart", "fastapi", "starlette", "uvicorn"):
        try:
            print("  %-20s %s" % (pkg, md.version(pkg)))
        except Exception:
            print("  %-20s (未安装)" % pkg)
except Exception as exc:
    print("  ★ ", exc)
