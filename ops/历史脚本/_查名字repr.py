#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打印含 3000 的产物文件名的 repr，用于核对归档标记为什么没匹配上。"""
import os

OUT = "/data/eia_report_gen/_生成结果"
for n in sorted(os.listdir(OUT)):
    if "3000" in n:
        print(repr(n))
        print("  含标记「某 3000 吨塑料制品生产线」:", "某 3000 吨塑料制品生产线" in n)
