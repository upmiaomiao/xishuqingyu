#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查那份来历不明的草稿：读它的正文，判断是测试输入还是真实项目。"""
import glob
import os
import re
import zipfile

OUT = "/data/eia_report_gen/_生成结果"
cands = glob.glob(os.path.join(OUT, "*20260918-094828*.docx"))
if not cands:
    print("文件不在了")
    raise SystemExit(0)
p = cands[0]
print("文件：%s" % os.path.basename(p))
print("大小：%d 字节" % os.path.getsize(p))

with zipfile.ZipFile(p) as z:
    xml = z.read("word/document.xml").decode("utf-8", "replace")
# 去标签取纯文本
text = re.sub(r"<w:p[ >]", "\n<w:p ", xml)
text = re.sub(r"<[^>]+>", "", text)
text = re.sub(r"\n{2,}", "\n", text).strip()

print("正文长度：%d 字" % len(text))
print()
print("=========== 正文前 1500 字 ===========")
print(text[:1500])
print()
print("=========== 找「项目名称」那一行 ===========")
for line in text.split("\n"):
    if "项目名称" in line or "建设单位" in line:
        print("  %s" % line.strip()[:120])
print()
print("=========== 判断 ===========")
markers = {
    "含「虚构示例」": "虚构示例" in text,
    "含测试特征词(测试/示例/演示)": any(k in text for k in ("测试", "示例", "演示")),
    "项目名称为空/未命名": "未命名" in text or "项目名称：\n" in text,
}
for k, v in markers.items():
    print("  %-28s %s" % (k, v))
