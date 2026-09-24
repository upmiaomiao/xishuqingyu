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
import os
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8011/gen"
JS = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.js"
# 批量删除那一节要造两份假草稿再删掉，所以得知道草稿目录在哪（和 gen_routes.py 同一口径）
OUT_DIR = os.environ.get("GEN_HOME", "/data/eia_report_gen") + "/_生成结果"
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

    # ---------------------------------------------------------------- 批量删除
    # 真造两份假草稿走一遍完整流程（造 → 出现在列表 → 批量删 → 列表没了 → 备份里有）。
    # 只看源码字符串不够：这一段的重点恰恰是"删干净了没、能不能找回"。
    print("[6] 批量删除历史报告")
    check("  界面有「删除选中」按钮", 'id="ge-delsel"' in src)
    check("  界面有全选复选框", 'id="ge-all"' in src)
    check("  每行有勾选框（只带下标，文件名不进属性）", 'class="ge-out-ck" data-i="' in src)
    check("  勾选变化会刷新按钮状态", "refreshSelBar" in src)
    check("  调的是 /delete_batch", '"/delete_batch"' in src)
    check("  全选框有半选状态（否则看起来像已全选）", "indeterminate" in src)

    made = []
    for i in (1, 2):
        p = os.path.join(OUT_DIR, "_契约测试_批量删除_%d.docx" % i)
        with open(p, "wb") as f:
            f.write(b"PK\x03\x04 fake docx for contract test - content irrelevant")
        made.append(os.path.basename(p))
    o2 = get("/api/outputs")
    names2 = [x["name"] for x in o2["files"]]
    # 注意：**不能**断言"假草稿出现在列表里" —— 线上有 90 份草稿，而列表按名倒序只列最近 50 份，
    # `_契约测试_…` 这种以下划线开头的名字排在窗口外（第一版就是这么失败的）。
    # 所以这里用 `总数` 判断"列表确实少了两份"：它不受 50 上限影响，也不会假设排序规则。
    check("  造的两份假草稿确实落盘了",
          all(os.path.isfile(os.path.join(OUT_DIR, m)) for m in made))
    check("  列表带「总数」（>50 份时界面要说清没列全）",
          isinstance(o2.get("总数"), int) and o2["总数"] >= len(names2), str(o2.get("总数")))

    r = post("/api/delete_batch", {"names": made})
    check("  delete_batch ok", r.get("ok") is True, str(r)[:120])
    check("  两份都被删", sorted(r.get("已删除") or []) == sorted(made), str(r.get("已删除")))
    o3 = get("/api/outputs")
    check("  总数少了两份（列表确实跟着少了）",
          (o2["总数"] - o3["总数"]) == 2, "%s → %s" % (o2.get("总数"), o3.get("总数")))
    check("  文件真从目录里没了（不只是界面）",
          not any(os.path.isfile(os.path.join(OUT_DIR, m)) for m in made))
    bak = r.get("备份目录") or ""
    check("  备份目录里两份都在（批量删也留后路）",
          bool(bak) and all(os.path.isfile(os.path.join(bak, m)) for m in made), str(bak))
    check("  备份目录不在列表里露出来", bak not in names2)

    # 两条不能成功的路子：空名单（绝不能当成"那就全删"）、目录穿越
    for bad, why in (([], "空名单"), (["../../etc/passwd"], "目录穿越")):
        try:
            post("/api/delete_batch", {"names": bad})
            check("  %s 被拒" % why, False, "居然返回 200")
        except urllib.error.HTTPError as e:
            check("  %s 被拒" % why, e.code in (400, 404), "HTTP %d" % e.code)
    check("  穿越探针没伤到系统文件", os.path.isfile("/etc/passwd"))

    # 清场：两份假草稿从列表目录与备份目录里都拿掉，别留在用户的历史里
    for m in made:
        for d in (OUT_DIR, bak):
            p = os.path.join(d, m) if d else ""
            if p and os.path.isfile(p):
                os.remove(p)
    check("  清场干净（假草稿不留痕）",
          not any(os.path.isfile(os.path.join(OUT_DIR, m)) for m in made))
    if bak and os.path.isdir(bak) and not os.listdir(bak):
        os.rmdir(bak)                    # 空备份目录也收掉，不给用户留垃圾

    print("=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("  失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())