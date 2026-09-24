# -*- coding: utf-8 -*-
"""看一眼锚定数组的顺序与页码：为什么批注视图打开了却落在第 1 页。"""
import json
import os
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:8011"
name = sys.argv[1]
url = BASE + "/audit/api/annot/" + urllib.parse.quote(name) + "?parse=0"
j = json.load(urllib.request.urlopen(url, timeout=600))
print("ok=%s anchors=%d pages=%s" % (j.get("ok"), len(j.get("anchors") or []), j.get("pages")))
print("定位统计:", j.get("定位统计"))
print("\n前 8 条（数组顺序）：")
for a in (j.get("anchors") or [])[:8]:
    print("  第%-3s条 %-24s %-8s page=%-5s level=%-5s" % (
        a.get("item"), (a.get("审核项") or "")[:22], a.get("结论"), a.get("page"), a.get("level")))
bad = [a for a in (j.get("anchors") or [])
       if a.get("page") and a.get("结论") in ("存在问题", "存在疑似问题", "优化调整建议")]
print("\n带页码的问题类锚定：%d 条" % len(bad))
if bad:
    f = bad[0]
    print("数组里第一条：第%s条 %s 结论=%s page=%s" % (f.get("item"), f.get("审核项"), f.get("结论"), f.get("page")))
    mn = min(bad, key=lambda a: a["page"])
    print("页码最小的那条：第%s条 %s 结论=%s page=%s" % (mn.get("item"), mn.get("审核项"), mn.get("结论"), mn.get("page")))
print("\n统计:", json.dumps(j.get("统计"), ensure_ascii=False))
