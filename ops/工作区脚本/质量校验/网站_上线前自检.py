#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""上线前静态自检：
  1) Python 语法编译
  2) 从内嵌 HTML 里抽出 <script> 交给 node --check 做 JS 语法校验
  3) 关键标签配对/锚点抽查

用法：python 网站_上线前自检.py 目标文件.py
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile

path = sys.argv[1]
src = open(path, encoding="utf-8").read()

# 1) Python 语法
import py_compile
try:
    py_compile.compile(path, cfile=os.path.join(tempfile.gettempdir(), "site_check.pyc"),
                       doraise=True)
    print("[1/3] Python 语法 OK")
except py_compile.PyCompileError as e:
    print("[1/3] Python 语法错误：", e)
    sys.exit(1)

# 2) 抽出内嵌 <script> 做 JS 语法校验（P3 之后前端已外置：优先查 frontend/index.html）
m = re.search(r"<script>(.*?)</script>", src, re.S)
fe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(path))), "frontend", "index.html")
if not m and os.path.isfile(fe):
    src_fe = open(fe, encoding="utf-8").read()
    m = re.search(r"<script>(.*?)</script>", src_fe, re.S)
    print(f"[2/3] 前端已外置，改查 {os.path.relpath(fe, os.path.dirname(os.path.dirname(fe)))}")
if not m:
    print("[2/3] 没找到 <script> 块")
    sys.exit(1)
js = m.group(1)
tmp = os.path.join(tempfile.gettempdir(), "site_embed.js")
open(tmp, "w", encoding="utf-8").write(js)
r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
if r.returncode == 0:
    print(f"[2/3] 内嵌 JS 语法 OK（{len(js)} 字符）")
else:
    print("[2/3] 内嵌 JS 语法错误：")
    print(r.stdout or r.stderr)
    sys.exit(1)

# 3) 关键锚点抽查
checks = {
    "请求模型含 image 字段": "image: str | None = Field(" in src,
    "图片校验函数": "def normalize_image(" in src,
    "识图函数": "async def read_image(" in src,
    "多模态消息构造": "def user_message(" in src,
    "识图结果拆分": "def split_read_result(" in src,
    "识图与检索并行": "vision_task = asyncio.create_task(read_image(image))" in src,
    "流式端点带图": "yield sse_event(\"vision\"" in src,
    "前端上传控件": 'id="fileInput"' in src,
    "前端压缩函数": "function scaleTo(" in src,
    "前端发送带图": "image:sentImage?sentImage.full:null" in src,
    "历史缩略图渲染": 'class="msg-img"' in src,
    "识别结果显示": "class=\"vision-box\"" in src,
    "配额兜底": "配额满" in src,
    "现场照片契约": "PHOTO_JSON_CONTRACT" in src,
    "JSON 渲染器": "def render_photo_report(" in src,
    "JSON 解析器": "def extract_json_object(" in src,
    "项目库词表": "PHOTO_ITEM_BANK" in src,
    "三态词表": "PHOTO_VERDICTS" in src,
    "固定结论边界": "PHOTO_REPORT_FOOTER" in src,
    "依据白名单校验": "def verify_citations(" in src,
    "研判独立通路": 'request.report == "photo"' in src,
    "前端研判开关": 'id="photoMode"' in src,
    "表格渲染": "md-table" in src,
    "旧契约已移除": "PHOTO_REPORT_SYSTEM" not in src,
}
bad = [k for k, v in checks.items() if not v]
for k, v in checks.items():
    print(f"      {'✓' if v else '✗'} {k}")
print("[3/3] " + ("锚点抽查全部通过" if not bad else f"缺少：{bad}"))
sys.exit(0 if not bad else 1)
