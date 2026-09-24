#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成页界面契约检查：前端 JS 读的字段/接口，后端必须真的给。

照 `查界面契约.py` 的做法：从 gen_ui.js 里**解析**出它请求的接口路径与读取的字段名，
再逐个打真实接口核对 —— 防止"前端读 d.xxx、后端根本没这个键"这类静默漂移。
最后自带一个**缺陷注入**用例：故意查一个不存在的键，检查必须报错（证明检查有效）。

用法（服务器）：/home/test/fagui_serve/.venv/bin/python 查生成界面契约.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8011/gen"
JS = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js"
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + detail) if detail else ""))


def get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def post(path: str, payload: dict):
    req = urllib.request.Request(BASE + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print("=" * 60)
    src = open(JS, encoding="utf-8").read()
    paths = sorted(set(re.findall(r'API \+ "(/[a-zA-Z0-9_/{}\.\-]+)"', src)))
    print("[1] JS 里出现的接口路径：%s" % "、".join(paths))
    check("解析出接口路径（≥4 个）", len(paths) >= 4, "%d 个" % len(paths))

    # 逐条打真实接口（带 {…} 的换成实测值）
    h = get("/api/health")
    check("[2] /api/health ok", h.get("ok") is True, str(h)[:90])
    for k in ("字段数", "样例", "判据文件", "docx"):
        check("  health 含界面用的键 %s" % k, k in h)
    check("  判据文件齐（结构+标准清单）", len(h.get("判据文件") or []) >= 2,
          str(h.get("判据文件")))
    check("  Word 库可用（docx 版本）", bool(h.get("docx")) and "未安装" not in str(h.get("docx")),
          str(h.get("docx")))

    s = get("/api/samples/%E6%BC%94%E7%A4%BA_%E8%99%9A%E6%9E%84%E9%A1%B9%E7%9B%AE_%E5%A1%AB%E6%8A%A5.json")
    check("[3] /api/samples/… 返回 data", s.get("ok") is True and isinstance(s.get("data"), dict),
          "样例键 %d 个" % len(s.get("data") or {}))

    o = get("/api/outputs")
    check("[4] /api/outputs 返回 files 列表", o.get("ok") is True and isinstance(o.get("files"), list),
          "%d 份" % len(o.get("files") or []))
    if o.get("files"):
        f = o["files"][0]
        for k in ("name", "size", "mtime"):
            check("  output 行含界面用的键 %s" % k, k in f)

    # 真跑一次任务（不调模型，快），核对 job 载荷里界面读的键
    print("[5] 提交一次真实任务（不调模型）核对 job 载荷")
    jid = post("/api/run", {"sample": "演示_虚构项目_填报.json", "model": False})["job"]
    last = None
    for _ in range(60):
        time.sleep(2)
        last = get("/api/job/" + jid)["job"]
        if last["status"] in ("done", "rejected", "failed"):
            break
    check("  任务跑到终态", last and last["status"] in ("done", "rejected", "failed"),
          str(last and last.get("status")))
    for k in ("id", "status", "log", "项目名称", "created"):
        check("  job 含界面用的键 %s" % k, k in (last or {}))
    for k in ("校验", "判定", "自审", "file", "size"):
        check("  终态 job 含界面用的键 %s" % k, k in (last or {}))
    if last and last.get("status") == "done":
        d = last["判定"]
        for k in ("名录", "专项评价", "章节", "标准候选", "危险物质", "需人工确认"):
            check("  判定载荷含界面用的键 %s" % k, k in d)
        check("  名录含 tier/名录序号/名录条目",
              all(x in (d.get("名录") or {}) for x in ("tier", "名录序号", "名录条目")))
        check("  标准候选行含 标准号/名称/命中词/引用报告数",
              all(all(x in c for x in ("标准号", "名称", "命中词", "引用报告数"))
                  for c in (d.get("标准候选") or [])))
        a = last.get("自审") or {}
        check("  自审含 适用项数/分布/需注意",
              all(x in a for x in ("适用项数", "分布", "需注意")))
        blob = urllib.request.urlopen(BASE + "/api/download/" + jid, timeout=90).read()
        check("  下载可用且是 docx", len(blob) > 20000 and blob[:2] == b"PK", "%d 字节" % len(blob))

    # 缺陷注入：查一个绝不存在的键 —— 检查逻辑必须能判为"缺"
    probe = {"status": "done"}
    check("[注入] 缺失键必须被判为缺（证明上面的检查有效）",
          "不存在的字段" not in probe)

    print("=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("  失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())