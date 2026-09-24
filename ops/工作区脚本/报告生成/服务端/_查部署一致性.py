#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""（已并入统一工具）本脚本原来用**写死的期望 md5** 校验部署一致性。

为什么改掉：写死 md5 的检查有个致命毛病 —— 一旦**正常部署**了新版本，
它就报"不一致"，于是变成"狼来了"，最后没人看。
2026-09-19 核查时它报的 9 项里，有 7 项其实是**线上比本地新**（本地部署源才是旧的），
与"部署不一致"是两回事。

现在统一用 `_脚本代码/服务器运维/核对镜像.py`：**以线上为准**做比对，
并区分「内容不一致 / 仅换行符不同 / 本地多出 / 本地缺失 / 有意不一致」。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[3]
TOOL = WS / "_脚本代码" / "服务器运维" / "核对镜像.py"

print(__doc__)
print(f"→ 改用：{TOOL.relative_to(WS)}\n")
sys.exit(subprocess.call([sys.executable, str(TOOL), *sys.argv[1:]]))
