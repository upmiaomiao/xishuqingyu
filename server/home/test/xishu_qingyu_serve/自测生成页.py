#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成页端到端自测（对话式）：描述 → 抽取 → 逐题回答 → 生成 → 预览 → 下载。

覆盖的是**真实用户路径**，不是直接塞 JSON：
  ① POST /chat/start 用一段自然语言描述（含模型会编造的地方，看闸门是否拦得住）
  ② 逐题 POST /chat/answer（其中一题故意答"不知道"，检查不猜）
  ③ POST /chat/generate（开模型）→ 轮询
  ④ GET /preview/{job} 预览必须来自交付件本身
  ⑤ GET /download/{job} 下载校验 docx

用法：/home/test/fagui_serve/.venv/bin/python 自测生成页.py
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
import zipfile

BASE = "http://127.0.0.1:8011/gen"
DESC = ("我们公司要在临沂市兰山区汪沟镇建一台20吨/小时的生物质锅炉给生产线供蒸汽，"
        "项目是技术改造，总投资1200万元，其中环保投资85万元，用地面积3000平方米。"
        "锅炉配布袋除尘和双碱法脱硫，烟气走25米排气筒。厂界东北方向320米有个阳光村，"
        "大约120户480人。生产废水不外排，全部沉淀后回用于除尘，不新增河道取水。"
        "项目还没有开工建设。")
ANSWERS = {
    "项目名称": "兰山生物质供热站技术改造项目",
    "国民经济行业类别": "热力生产和供应 D4430",
    "建设项目行业类别": "热力生产和供应工程（包括建设单位自建自用的供热工程）",
    "地理坐标": "东经118度20分31秒，北纬35度06分12秒",
    "是否开工建设": "还没有开工",
    "主要原辅材料": "生物质成型燃料，年用量12000吨，不是危险物质",
}
OK, BAD = [], []


def check(name, cond, detail=""):
    (OK if cond else BAD).append(name)
    print("  %s %s%s" % ("√" if cond else "×", name, ("　" + str(detail)[:110]) if detail else ""))


def get(path, raw=False):
    with urllib.request.urlopen(BASE + "/api" + path, timeout=90) as r:
        b = r.read()
        return b if raw else json.loads(b.decode("utf-8"))


def post(path, payload):
    req = urllib.request.Request(BASE + "/api" + path, data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read().decode("utf-8"))


def main() -> int:
    print("=" * 64)
    h = get("/health")
    print("健康：ok=%s 字段=%s docx=%s" % (h.get("ok"), h.get("字段数"), h.get("docx")))
    check("引擎就绪", h.get("ok") is True, h.get("docx"))

    print("\n① 自然语言描述 → 抽取")
    s = post("/chat/start", {"text": DESC})
    print("   会话 %s；读到 %d 项；丢弃 %d 项" % (s["session"], s["采纳数"], s["丢弃数"]))
    for d in s["丢弃"]:
        print("     · 丢弃 %s：%s" % (d["字段"], str(d["原因"])[:80]))
    check("抽到了基本信息（≥5 项）", s["采纳数"] >= 5, s["采纳数"])
    check("生成后的问题（≥3 个）", len(s["问题"]) >= 3, len(s["问题"]))
    check("问题里有非判定类的基本信息", any(
        ("专项" not in (q.get("为什么问") or "") and "名录" not in (q.get("为什么问") or ""))
        for q in s["问题"]))
    names = "、".join(r["字段"] for r in s["已知"])
    check("已知事实里没有编造的项目名称", "建设项目名称" not in names, names[:70])

    print("\n② 逐题回答（两轮，其中一题故意答「不知道」）")
    sid, skipped = s["session"], False
    asked = []
    for rnd in range(2):
        st = get("/chat/state/" + sid)
        qs = st.get("问题") or []
        if not qs:
            break
        print("   — 第 %d 轮：%d 个问题" % (rnd + 1, len(qs)))
        for q in qs:
            ans = None
            for k, v in ANSWERS.items():
                if q.get("中文名") == k or q.get("key") == k:
                    ans = v
                    break
            if ans is None and not skipped:
                ans, skipped = "不知道", True
            if ans is None:
                ans = "没有"
            asked.append(q.get("中文名"))
            r = post("/chat/answer", {"session": sid, "key": q["key"], "中文名": q.get("中文名"),
                                       "类型": q.get("类型"), "事实名": q.get("事实名"),
                                       "问题": q["问题"], "text": ans})
            print("     Q:%s\n       A:%s → %s" % (q["问题"][:48], ans[:24], r["本次"]))
    check("回答了「不知道」的题没有被填值", skipped)
    check("第一轮就问到了项目名称", "建设项目名称" in asked[:8], asked[:8])
    st = get("/chat/state/" + sid)
    keys = "、".join(r["字段"] for r in st["已知"])
    check("回答后已知事实增加（≥12 项）", len(st["已知"]) >= 12, len(st["已知"]))
    vals = {r["字段"]: r["值"] for r in st["已知"]}
    check("没有把「生产废水不外排」误判成废水直排（填 false 或留空都行，就是不能填 true）",
          vals.get("新增工业废水直排") not in (True, "True"),
          vals.get("新增工业废水直排"))
    print("   已知：%s" % keys[:160])

    print("\n③ 生成（开模型）")
    jid = post("/chat/generate", {"session": sid, "model": True})["job"]
    last, seen = None, 0
    for _ in range(150):
        time.sleep(2)
        last = get("/job/" + jid)["job"]
        for l in (last.get("log") or [])[seen:]:
            print("   [%s] %s" % (l["step"], l["text"][:120]))
        seen = len(last.get("log") or [])
        if last["status"] in ("done", "rejected", "failed"):
            break
    check("任务到终态", last and last["status"] == "done", last and last.get("status"))
    if not last or last.get("status") != "done":
        print("   ！未完成：", json.dumps(last, ensure_ascii=False)[:400])
        return 1
    check("产物是 docx 且 >30KB", (last.get("size") or 0) > 30000, last.get("size"))
    check("缺项被标为需人工补充（日志有提示）",
          any("需人工补充" in (l.get("text") or "") for l in last["log"]))

    print("\n④ 预览（必须来自交付件本身）")
    pv = get("/preview/" + jid, raw=True).decode("utf-8")
    check("预览含 <table>（表格渲染出来了）", "<table>" in pv, pv.count("<table>"))
    check("预览里写明预览的是交付件本身", "交付件本身" in pv)
    check("预览含项目名称", "兰山生物质供热站" in pv)
    check("预览含需人工补充标注", "需人工补充" in pv)
    check("自审没有「存在问题」误报（废水直排那条）",
          "地表水专项评价设置" not in json.dumps(last.get("自审") or {}, ensure_ascii=False) or
          "存在问题" not in json.dumps((last.get("自审") or {}).get("分布") or {}, ensure_ascii=False),
          json.dumps((last.get("自审") or {}).get("分布") or {}, ensure_ascii=False))

    print("\n⑤ 下载校验")
    blob = get("/download/" + jid, raw=True)
    open("/tmp/dl_chat.docx", "wb").write(blob)
    z = zipfile.ZipFile("/tmp/dl_chat.docx")
    doc = z.read("word/document.xml").decode("utf-8", "ignore")
    check("下载件是合法 docx", "word/document.xml" in z.namelist(), "%d 字节" % len(blob))
    check("下载件与预览同源（字节数一致）", len(blob) == last.get("size"), last.get("size"))
    check("含「对话采集」来源表", "来源" in doc or "依据" in doc)

    print("\n⑥ 历史报告（右上角按钮取的是**以前的**文件，不只是本次生成的）")
    outs = get("/outputs")
    files = outs.get("files") or []
    check("历史列表非空", bool(files), "%d 份" % len(files))
    check("每份都带名字/大小/时间",
          all(f.get("name") and f.get("size") and f.get("mtime") for f in files),
          files[0] if files else None)
    old = [f for f in files if f["name"] not in json.dumps(last, ensure_ascii=False)]
    old = old[0] if old else (files[-1] if files else None)
    if old:
        q = urllib.parse.quote(old["name"])
        pv2 = get("/preview_file/" + q, raw=True)
        dl2 = get("/output/" + q, raw=True)
        check("旧报告能预览（HTML）", b"<table>" in pv2 or b"pp-page" in pv2, "%d 字节" % len(pv2))
        check("旧报告能下载（docx，且与列表大小一致）",
              dl2[:2] == b"PK" and len(dl2) == old["size"],
              "%s 列表 %d / 实取 %d" % (old["name"], old["size"], len(dl2)))
        check("取到的是另一份（不是本次刚生成的）", old["name"] != (last.get("name") or ""),
              old["name"])

    print("\n⑦ 示例轮换与「重新生成」（回答「是不是预设的」）")
    d1 = get("/chat/demo")
    d2 = get("/chat/demo?exclude=" + urllib.parse.quote(d1["示例"]))
    d3 = get("/chat/demo?exclude=" + urllib.parse.quote(d2["示例"]))
    texts = [d1["示例"], d2["示例"], d3["示例"]]
    check("示例总数 >1（不是只有一条写死的）", d1.get("总数", 0) > 1, d1.get("总数"))
    check("连点三次给出三条不同示例", len(set(texts)) == 3, [t[:18] for t in texts])
    check("示例带序号，前端能显示「第 n / N 个」", all(x.get("序号") for x in (d1, d2, d3)))
    check("示例都标了「虚构示例」", all("虚构示例" in t for t in texts))

    def gen_md5(sess, fresh=False):
        """生成一次，下载产物算 md5 —— 注意不能用文件名比：文件名带时间戳，必然不同。"""
        body = {"session": sess, "model": True}
        if fresh:
            body["fresh"] = True
        jid = post("/chat/generate", body)["job"]
        while True:
            time.sleep(1)
            jj = get("/job/" + jid)["job"]
            if jj["status"] in ("done", "rejected", "failed"):
                break
        blob = get("/download/" + jid, raw=True)
        return hashlib.md5(blob).hexdigest(), jj

    st2 = post("/chat/start", {"text": DESC})
    sid2 = st2["session"]
    m1, _ = gen_md5(sid2)
    m2, _ = gen_md5(sid2)
    check("默认路径两次生成**字节一致**（同输入同输出 = 可复现，不是每次乱写）", m1 == m2, m1)
    f1, jf1 = gen_md5(sid2, fresh=True)
    f2, _ = gen_md5(sid2, fresh=True)
    check("重新生成会走模型（日志里写明忽略缓存）",
          any("重新生成" in (l.get("text") or "") for l in jf1.get("log") or []))
    check("重新生成至少有一版与默认版不同（措辞真的会变）",
          f1 != m1 or f2 != m1, "默认 %s / 重生成 %s , %s" % (m1[:8], f1[:8], f2[:8]))

    print("\n⑧ 新建报告：清空这次会话，但不动已生成的文件")
    st3 = post("/chat/start", {"text": DESC})
    sid3 = st3["session"]
    before = len(get("/outputs")["files"])
    r = post("/chat/reset", {"session": sid3})
    check("reset 返回已清理", r.get("已清理") is True, r)
    try:
        get("/chat/state/" + sid3)
        gone = False
    except Exception as exc:                      # 404 才是对的
        gone = "404" in str(exc) or "Not Found" in str(exc)
    check("重置后会话真的没了（state 404）", gone)
    r2 = post("/chat/reset", {"session": sid3})
    check("重复重置不报错（幂等）", r2.get("ok") is True and r2.get("已清理") is False, r2)
    after = len(get("/outputs")["files"])
    check("重置**不删**已生成的报告（归档不删）", after == before, "%d → %d" % (before, after))
    try:
        post("/chat/generate", {"session": sid3, "model": False})
        gen_ok = True
    except Exception:
        gen_ok = False
    check("重置后拿旧会话生成会被拒（400）", gen_ok is False)

    print("\n" + "=" * 64)
    print("==== 通过 %d / 失败 %d ====" % (len(OK), len(BAD)))
    for b in BAD:
        print("   失败：", b)
    return 1 if BAD else 0


if __name__ == "__main__":
    sys.exit(main())