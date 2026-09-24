#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""验证"查未导入名字.py"这个检查器**真的能抓到**它要抓的 bug。

检查器本身也要被检查 —— 本会话已经吃过几次亏：断言写错、DOM 桩写错、
采样不足被当成真失败。一个永远返回 OK 的检查器比没有检查器更危险。
这里用"注入故障 + 确认报错 + 还原"的方式自证。
"""
from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

W = pathlib.Path(r"_中间产物/重构工作区/xishu_pipeline")
CHECKER = pathlib.Path(r"_脚本代码/站点全量测试/查未导入名字.py")
TARGET = W / "routes.py"


def run_checker() -> tuple[int, str]:
    r = subprocess.run([sys.executable, str(CHECKER)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def py_compile(path: pathlib.Path) -> tuple[int, str]:
    r = subprocess.run([sys.executable, "-m", "py_compile", str(path)],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")

    # ---- 1) 干净状态下应该是 OK ----
    rc, out = run_checker()
    print("① 干净状态          → 退出码 %d  %s" % (rc, "全部 OK" if "全部 OK" in out else "有发现问题"))
    assert rc == 0, "干净状态下检查器不该报错"

    # ---- 2) 注入故障：把 error_body 从导入里去掉（就是上午那次线上事故）----
    broken = original.replace("error_body, format_validation_error", "format_validation_error")
    assert broken != original, "注入失败：没找到要替换的文本"
    TARGET.write_text(broken, encoding="utf-8")
    try:
        rc2, out2 = run_checker()
        caught = "error_body" in out2 and rc2 != 0
        print("② 注入 error_body 缺失 → 退出码 %d  %s"
              % (rc2, "★ 抓到了" if caught else "!! 没抓到（检查器失效）"))
        assert caught, "检查器没抓到注入的 bug"

        # ---- 3) 对照：py_compile 对同一份坏文件是什么反应 ----
        rc3, out3 = py_compile(TARGET)
        print("③ 同一份坏文件 py_compile → 退出码 %d  %s"
              % (rc3, "语法 OK（查不出来）" if rc3 == 0 else "语法错误"))
        assert rc3 == 0, "py_compile 本应对这份文件说 OK —— 这正是它漏掉事故的原因"
    finally:
        TARGET.write_text(original, encoding="utf-8")

    # ---- 4) 还原后必须回到 OK ----
    rc4, out4 = run_checker()
    print("④ 还原后            → 退出码 %d  %s" % (rc4, "全部 OK" if "全部 OK" in out4 else "仍有问题"))
    assert rc4 == 0, "还原后检查器仍在报错"
    assert TARGET.read_text(encoding="utf-8") == original, "还原不完整"

    print()
    print("检查器自证通过：能抓到 NameError 类缺陷，且 py_compile 确实抓不到。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
