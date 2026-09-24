#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查半成品向量：index_p6/vectors.npy 里前多少行是真向量、从哪里开始是零。

为什么必须查：续跑要靠"已完成行数"，如果这个数比真实值大，
中间那段就是**零向量**（检索里等于这些块永远召不回），而且不会有任何报错。
"""
from __future__ import annotations

import sys

import numpy as np

p = sys.argv[1] if len(sys.argv) > 1 else "/data/fagui_rag/index_p6/vectors.npy"
v = np.load(p, mmap_mode="r")
print("形状：%s ｜ 文件 %.0f MB" % (v.shape, v.nbytes / 1024 / 1024))

# 分片扫描找"第一个全零行"（一次性算整份会吃 1.4 GB 内存）
first_zero = None
nz = 0
STEP = 20000
for s in range(0, v.shape[0], STEP):
    blk = np.asarray(v[s:s + STEP])
    z = np.all(blk == 0, axis=1)
    nz += int((~z).sum())
    if first_zero is None and z.any():
        first_zero = s + int(np.argmax(z))
print("非零行：%d ／ 共 %d" % (nz, v.shape[0]))
print("第一个全零行：%s" % ("无（全部已嵌）" if first_zero is None else first_zero))
