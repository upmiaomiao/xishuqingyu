# -*- coding: utf-8 -*-
"""本地裁剪：把服务器渲好的整页 PNG 裁出批注附近，便于肉眼看"框得准不准"。

用法：python 裁批注页.py <输入png> <输出png> <页宽pt> <页高pt> <x0> <y0> <x1> <y1>
坐标是 PDF 的 pt（左上原点），按 PNG 实际像素自动换算。
"""
import sys

from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
pw, ph = float(sys.argv[3]), float(sys.argv[4])
x0, y0, x1, y1 = (float(v) for v in sys.argv[5:9])
im = Image.open(src)
sx, sy = im.width / pw, im.height / ph
pad = 30
box = (max(0, int((x0 - pad) * sx)), max(0, int((y0 - pad - 14) * sy)),
       min(im.width, int((x1 + pad) * sx)), min(im.height, int((y1 + pad) * sy)))
im.crop(box).save(dst)
print("%s → %s  %s" % (src, dst, box))
