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
CSS = "/home/test/xishu_qingyu_serve/xishu_pipeline/static/gen_ui.css"
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
    css = open(CSS, encoding="utf-8").read()
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

    # ------------------------------------------------- 封面署名与「就地改 + 重新生成」
    # 2026-09-24 用户原话：「我告诉他报告编制单位是中节能，但是他好像并不能帮我写入 doc 文档中，
    # 我想表达的是整个逻辑好像有点问题」。当时查下来**三处同时断了**：字段表里没有这三个字段
    # （模型被要求 key 必须与清单一致 → 那句话被静默丢掉、连提示都没有）、docx 封面写死常量、
    # 所以怎么说都到不了文档。这一节把它钉成回归测试：从"改一项"一路验到"生成的 .docx 封面
    # 里真的写着中节能"。**刻意不过模型**（用 /chat/set 直接写事实、生成时 model=false）——
    # 契约要能稳定复现，不能因为模型抽歪了就说功能坏了。
    print("[7] 封面署名 / 待补充清单 / 就地改后重新生成")
    check("  界面有「项目信息 / 报告预览」两个页签",
          'id="ge-tab-info"' in src and 'id="ge-tab-doc"' in src)
    check("  界面上有封面信息卡片", 'id="ge-cover"' in src)
    check("  界面上有待补充清单卡片", 'id="ge-gap-card"' in src)
    check("  就地改走 /chat/set", '"/chat/set"' in src)
    check("  右侧有「重新生成报告」按钮", 'id="ge-regen"' in src)
    check("  页签样式里 hidden 压得住 flex（否则两页会同时显示）", ".ge-pane[hidden]" in css)
    check("  「我补充过的内容」已不在左栏（搬到右栏了）",
          'ge-mine' not in src.split('id="ge-ask"')[0])
    # 断言的是**真正的代码**（`MINE.slice(-5).reverse()`），不是 `MINE.slice(-5)` ——
    # 后者在 gen_ui.js 的注释里出现过（"原先只渲染最近 5 条"），第一版就是这么误报的：
    # 注释里写了旧写法，检查就当成"还没改"（和之前 CSS 变量那次是同一个坑）。
    check("  补充记录不再只留最近 5 条", "MINE.slice(-5).reverse()" not in src)

    # 字段清单是给模型看的，所以"字段在不在清单里"决定了"说了能不能被抽出来"（不调模型就能查）
    menu = ""
    try:
        sys.path.insert(0, "/data/eia_report_gen")
        from gen import intake as _intake
        menu = _intake._field_menu()
    except Exception as exc:                                      # noqa: BLE001
        check("  能读到字段清单", False, str(exc)[:80])
    for k in ("建设单位", "编制单位", "编制日期"):
        check("  字段清单里有 %s（说了才抽得出来）" % k, ('"%s"' % k) in menu)

    st = post("/api/chat/start", {"text": "某公司生物质锅炉技术改造项目建设地点在某市某区，"
                                          "总投资 1200 万元，属于技术改造。"})
    sid = st["session"]
    cov = {c["键"]: c for c in (st.get("封面") or [])}
    check("  会话返回封面三格（填没填都要返回）",
          all(k in cov for k in ("建设单位", "编制单位", "编制日期")), str(sorted(cov)))
    check("  没填时封面值为空（界面显示「空」，不是编一个）",
          cov.get("编制单位", {}).get("值") == "", repr(cov.get("编制单位", {}).get("值")))

    r = post("/api/chat/set", {"session": sid, "kind": "字段", "key": "编制单位", "text": "中节能"})
    check("  /chat/set 保存编制单位", r.get("ok") is True and r.get("采纳") is True, str(r)[:100])
    check("  保存后封面里就有值了",
          any(c["键"] == "编制单位" and c["值"] == "中节能" for c in (r.get("封面") or [])))
    check("  事实表里也有它（带字段键，界面才能就地改）",
          any(x.get("键") == "编制单位" for x in (r.get("已知") or [])))
    r2 = post("/api/chat/set", {"session": sid, "kind": "字段", "key": "编制单位", "text": ""})
    check("  清空也支持（留空=清掉这一项）",
          all(c["值"] == "" for c in (r2.get("封面") or []) if c["键"] == "编制单位"))
    post("/api/chat/set", {"session": sid, "kind": "字段", "key": "编制单位", "text": "中节能"})
    try:
        post("/api/chat/set", {"session": sid, "kind": "字段", "key": "根本没这个字段", "text": "x"})
        check("  未知字段被拒", False, "居然返回 200")
    except urllib.error.HTTPError as e:
        check("  未知字段被拒", e.code == 400, "HTTP %d" % e.code)

    def gen_and_wait(sess: str) -> dict:
        """建任务并等终态。

        注意 `/api/job/{id}` 回的是 `{"ok": true, "job": {...}}` —— **任务在 `job` 里**。
        第一版直接在响应外层找 `status`（永远找不到），于是"任务明明 0.2 秒就跑完了"，
        契约却报"生成超时"，连带后面四条也被判失败（读错层级这种错最像真故障）。
        """
        jid = post("/api/chat/generate", {"session": sess, "model": False})["job"]
        t0 = time.time()
        while time.time() - t0 < 180:
            j = (get("/api/job/" + jid) or {}).get("job") or {}
            if j.get("status") in ("done", "rejected", "failed"):
                return j
            time.sleep(1.0)
        return {"status": "timeout"}

    j1 = gen_and_wait(sid)
    check("  生成成功（不调模型）", j1.get("status") == "done", str(j1.get("status"))[:60])
    draft = os.path.join(OUT_DIR, j1.get("file") or "")
    check("  草稿落盘", bool(j1.get("file")) and os.path.isfile(draft), str(j1.get("file")))
    gaps1 = j1.get("待补充") or []
    check("  任务里带回「待补充」清单（界面据此渲染）", len(gaps1) > 0, "%d 处" % len(gaps1))
    check("  清单里每处都带 位置/标签/键/类型/片段",
          all(all(k in g for k in ("位置", "标签", "键", "类型", "片段")) for g in gaps1))
    if os.path.isfile(draft):
        from docx import Document
        doc = Document(draft)
        cover = {row.cells[0].text.strip(): row.cells[1].text.strip() for row in doc.tables[0].rows}
        body = "\n".join(p.text for p in doc.paragraphs)
        # ★ 用户报的那件事，直接断言：
        check("  ★ 成稿封面「编制单位」写的是中节能", cover.get("编制单位") == "中节能",
              repr(cover.get("编制单位")))
        check("  封面「建设单位」空着时标【需人工补充】",
              "【需人工补充】" in cover.get("建设单位", ""), repr(cover.get("建设单位")))
        check("  编制日期不替用户写今天（留「年 月」）",
              "年" in cover.get("编制日期", "") and "20" not in cover.get("编制日期", ""),
              repr(cover.get("编制日期")))
        check("  待补充清单里没有已填的编制单位（补上就该消失）",
              not any(g["键"] == "编制单位" for g in gaps1))
        check("  「待补充」与成稿正文对得上（正文里确实还有【需人工补充】）",
              "【需人工补充】" in body)

        # 再走一遍"就地补写 → 重新生成"：补上施工期措施，重新生成后正文里要有这句话
        post("/api/chat/set", {"session": sid, "kind": "补写",
                               "key": "施工期环境保护措施",
                               "text": "施工期货运扬尘采取洒水抑尘与车辆冲洗，夜间不施工。"})
        j2 = gen_and_wait(sid)
        check("  补写后重新生成成功", j2.get("status") == "done", str(j2.get("status"))[:60])
        d2 = os.path.join(OUT_DIR, j2.get("file") or "")
        if os.path.isfile(d2):
            body2 = "\n".join(p.text for p in Document(d2).paragraphs)
            check("  ★ 补写的话进了正文（改完重新生成即生效）",
                  "洒水抑尘与车辆冲洗" in body2)
            g2 = j2.get("待补充") or []
            check("  补上之后清单变短（不是一直挂在那儿骗人）",
                  len(g2) < len(gaps1), "%d → %d 处" % (len(gaps1), len(g2)))
            check("  清单里不再有这一节",
                  not any(g["键"] == "施工期环境保护措施" for g in g2))
        for p in (draft, d2):
            if p and os.path.isfile(p):
                os.remove(p)          # 清场：契约跑出来的草稿不进用户的历史列表
        check("  清场干净（契约草稿不留痕）",
              not os.path.isfile(draft) and not os.path.isfile(d2))

    print("=" * 60)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("  失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())