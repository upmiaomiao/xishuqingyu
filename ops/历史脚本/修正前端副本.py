#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修正工作副本：把过期的单体版 index.html 归档，换成线上那份。

起因：2026-09-18 我读工作副本的 index.html（41132 B 的单体版），
据此判断"前端还是一行、没模块化"—— 结论完全错了。
线上早就是 4251 B / 22 行的模块化版，`index.html.新` 就是它。

副本过期这件事本身很危险：它会让后续所有判断都建立在错误前提上。
这里把副本修正到与线上一致，并**归档而不是删除**旧单体版（保留取证价值）。
"""
from __future__ import annotations

import hashlib
import pathlib
import shutil

FRONT = pathlib.Path(r"_中间产物/重构工作区/frontend")
ARCH = pathlib.Path(r"_中间产物/重构工作区/_前端副本修正_20260918")
LIVE = pathlib.Path(r"_中间产物/重构工作区/_线上index.html")

TARGET = FRONT / "index.html"
NEW = FRONT / "index.html.新"


def md5(p: pathlib.Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def main() -> int:
    print("=" * 96)
    print("修正工作副本：index.html 换成线上版")
    print("=" * 96)

    stale = TARGET
    print("\n① 归档过期单体版")
    ARCH.mkdir(parents=True, exist_ok=True)
    keep = ARCH / "index.html.旧单体版"
    shutil.copy2(stale, keep)
    print("   %s  (%d B, md5 %s)" % (keep, keep.stat().st_size, md5(keep)))
    print("   ← 归档不是删除：这份是 41132 B 的单体版，"
          "含 22541 字符内联 <script> 与 12843 字符内联 <style>，留作取证")

    print("\n② 用线上版替换工作副本 index.html")
    before = md5(stale)
    shutil.copy2(LIVE, TARGET)
    after = md5(TARGET)
    print("   替换前 md5 %s" % before)
    print("   替换后 md5 %s  (%d B, %d 行)"
          % (after, TARGET.stat().st_size, len(TARGET.read_text(encoding="utf-8").split("\n"))))
    assert after == md5(LIVE), "替换后与线上不一致"
    assert after != before, "替换没生效"

    print("\n③ index.html.新 已完成使命，一并归档（避免以后再有人分不清哪份是准的）")
    keep2 = ARCH / "index.html.新"
    shutil.copy2(NEW, keep2)
    NEW.unlink()
    print("   %s" % keep2)
    print("   已从 frontend/ 移走 —— 从此 frontend/index.html 就是唯一权威副本")

    print("\n④ 修正后逐一核对工作副本 vs 线上")
    live_md5 = {
        "index.html": "c30f6b8cad7c9dc716ebcba28d5238f6",
        "app.css": "d96da08142bb18468da067903bb52e0c",
        "gen.html": "252382204f4cd315cbc451859051e227",
        "audit.html": "10c1db290a745806907d78ccdf31aece",
        "js/util.js": "eb9eadd47ad3757f9e67af43fe4e218d",
        "js/views.js": "6bf92bb18346c7b3256ed02b6fbfabd3",
        "js/message.js": "e58f7e57e9587ce47e6ae029bd1c40d1",
        "js/image.js": "cf20d1d32d9880881b40a163cb2bd0e0",
        "js/store.js": "576320e7770fdefcc45824c7f1b1d0b4",
        "js/kg.js": "f8b21192de644eb6108b72e1a09f0e00",
        "js/ask.js": "61da7261c74a6e2638a4c72b2a58f712",
        "js/main.js": "9652f2fa1154eb064b4688588c6821f0",
    }
    bad = 0
    for rel, want in live_md5.items():
        p = FRONT / rel
        if not p.exists():
            print("   × %-16s 副本缺失" % rel)
            bad += 1
            continue
        got = md5(p)
        ok = got == want
        print("   %s %-16s %s" % ("√" if ok else "×", rel, got))
        if not ok:
            bad += 1
    print()
    if bad:
        print("仍有 %d 个文件与线上不一致" % bad)
        return 1
    print("全部 12 个文件与线上逐字节一致 —— 工作副本现在可信了。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
