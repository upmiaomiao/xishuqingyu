#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网站服务端回归基线（重构安全网）。

在 .10 上用站点 venv 运行：
  /home/test/fagui_serve/.venv/bin/python 网站_回归基线.py <site.py> [--live]

分层：
  Tier A（默认，无模型调用）：纯函数 + 入口约束 + 静态页自检
  Tier B（--live，真实调用 v5，较慢）：4 条路由的事件形状

重构时 Tier A 必须始终全绿；Tier B 用于确认路由行为未变。
"""
from __future__ import annotations

import base64
import importlib
import importlib.util
import io
import json
import os
import re
import sys

SITE = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else \
    "/home/test/xishu_qingyu_serve/xishu_qingyu_qa.py"
# 抽包后的部署形态：入口是薄壳文件，真正的实现在同级 xishu_pipeline/。
# 传进来的是文件时，若同级存在 xishu_pipeline/，改按目录（包结构）被测，
# 否则会被当成"单文件单体"，断言全部找不到符号。
if os.path.isfile(SITE) and os.path.isdir(os.path.join(os.path.dirname(SITE), "xishu_pipeline")):
    SITE = os.path.dirname(SITE)
LIVE = "--live" in sys.argv
LIVE_BASE = "http://127.0.0.1:8011"
if "--base" in sys.argv:
    LIVE_BASE = sys.argv[sys.argv.index("--base") + 1].rstrip("/")

# 兼容两种形态：① 单文件单体；② 抽包后的站点目录（含 xishu_pipeline/）。
# 抽包形态下把各子模块的公开符号统一挂到一个 facade 上，使下面的断言不必区分形态。
if os.path.isdir(SITE):
    sys.path.insert(0, SITE)
    import xishu_pipeline.routes as _routes          # noqa: E402
    mod = _routes
    for _m in ("config", "prompts", "route", "textclean", "kg", "retrieve", "normalize",
               "compose", "understand", "postprocess", "llm", "splitter", "pipeline", "routes"):
        try:
            _sub = importlib.import_module(f"xishu_pipeline.{_m}")
        except Exception:
            continue
        for _k, _v in vars(_sub).items():
            if not _k.startswith("__"):
                setattr(mod, _k, _v)
    TARGET_DESC = f"包结构站点目录 {SITE}"
else:
    spec = importlib.util.spec_from_file_location("site_under_test", SITE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    TARGET_DESC = f"单文件 {SITE}"
print(f"被测目标：{TARGET_DESC}")

fails: list[str] = []
known: list[str] = []      # 已知遗留：测试正确、代码待修，不计入失败
group = ""


def G(name):
    global group
    group = name
    print(f"\n===== {name} =====")


def ck(desc, ok, detail="", is_known=False):
    if not ok:
        (known if is_known else fails).append(f"[{group}] {desc}")
    tag = "✓" if ok else ("⚠️" if is_known else "✗")
    print(f"{tag} {desc}" + (f"   {detail}" if detail and not ok else ""))


# ---------- 构造测试数据 ----------
def png_data_url(text="测试图片", size=(300, 120)) -> str:
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    font = None
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",):
        try:
            font = ImageFont.truetype(p, 20)
            break
        except Exception:
            pass
    d.text((10, 40), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ============================================================
G("1. 入口约束 normalize_image")
# ============================================================
ck("合法 PNG 通过", mod.normalize_image(png_data_url()) is not None)
ck("空值返回 None（不报错）", mod.normalize_image(None) is None and mod.normalize_image("") is None)
try:
    mod.normalize_image("data:text/plain;base64,aGk=")
    ck("非图片 MIME 应 400", False, "没有抛错")
except mod.HTTPException as e:
    ck("非图片 MIME 应 400", e.status_code == 400, f"实际 {e.status_code}")
try:
    mod.normalize_image("data:image/png;base64," + "A" * (mod.MAX_IMAGE_CHARS + 10))
    ck("超大图片应 413", False, "没有抛错")
except mod.HTTPException as e:
    ck("超大图片应 413", e.status_code == 413, f"实际 {e.status_code}")
try:
    mod.normalize_image("data:image/png,notbase64")
    ck("缺少 ;base64, 应 400", False, "没有抛错")
except mod.HTTPException as e:
    ck("缺少 ;base64, 应 400", e.status_code == 400, f"实际 {e.status_code}")

# ============================================================
G("2. 识图结果拆分 split_read_result")
# ============================================================
q, d = mod.split_read_result("这是问题？\n---\n详细转写内容\n第二行")
ck("标准格式正确拆分", q == "这是问题？" and "详细转写内容" in d, f"q={q!r} d={d[:20]!r}")
q2, d2 = mod.split_read_result("这是问题？\n\n---\n\n详细内容")
ck("--- 前后有空行也能拆", q2 == "这是问题？" and d2.startswith("详细内容"), f"q={q2!r}")
q3, d3 = mod.split_read_result("只有一段话没有分隔符")
ck("无分隔符时退化不崩", bool(q3) and bool(d3))
ck("空输入返回空", mod.split_read_result("") == ("", ""))

# ============================================================
G("3. JSON 提取器 extract_json_object")
# ============================================================
GOOD = {"image_type": "固废贮存堆场", "visible_facts": ["a"], "checklist": [],
        "risks": [], "waste_class": "x", "missing_info": [], "uncertainty": "y"}
js = json.dumps(GOOD, ensure_ascii=False)
ck("裸 JSON", mod.extract_json_object(js) is not None)
ck("```json 围栏", mod.extract_json_object(f"```json\n{js}\n```") is not None)
ck("think 块之后", mod.extract_json_object(f"推理…</think>\n{js}") is not None)
ck("前后有废话", mod.extract_json_object(f"好的：\n{js}\n以上。") is not None)
ck("坏 JSON → None", mod.extract_json_object('{"image_type": "x", ') is None)
ck("无 JSON → None", mod.extract_json_object("这是一段散文。") is None)

# ============================================================
G("4. 报告渲染器 render_photo_report")
# ============================================================
rep, st = mod.render_photo_report(GOOD)
for sec in ("【一、图片类型】", "【二、图中可见事实】", "【三、核验清单】", "【四、风险提示】",
            "【五、固废属性初判】", "【六、需要补充的信息】", "【七、结论边界】"):
    ck(f"含 {sec}", sec in rep)
ck("固定表头", "| 检查项 | 图中可见情况 | 判定 | 依据 |" in rep)
ck("表格分隔行", "| --- | --- | --- | --- |" in rep)
ck("正常输入无降级", st == {"dropped_items": 0, "coerced_verdicts": 0, "coerced_stance": 0}, str(st))

bad = dict(GOOD)
bad["checklist"] = [
    {"item": "防扬散（覆盖/围挡/喷淋）", "observed": "无", "verdict": "基本满足", "basis": "依据不足"},
    {"item": "现场整洁度", "observed": "乱", "verdict": "不满足", "basis": "依据不足"},
    {"item": "雨污分流", "observed": "a|b", "verdict": "无法判断", "basis": "依据不足"},
]
bad["risks"] = [{"level": "高", "stance": "可能已显示", "text": "x"}]
rep2, st2 = mod.render_photo_report(bad)
ck("越界判定降级为无法判断", st2["coerced_verdicts"] == 1, str(st2))
ck("库外检查项被丢弃", st2["dropped_items"] == 2, str(st2))
ck("越界风险立场被规范", st2["coerced_stance"] == 1, str(st2))
ck("被丢弃项不出现在报告", "现场整洁度" not in rep2)
empty_rep, _ = mod.render_photo_report({})
ck("空 JSON 也能产出完整骨架", "【七、结论边界】" in empty_rep)

# ============================================================
G("5. 依据白名单校验 verify_citations")
# ============================================================
SRC = [
    {"index": 1, "title": "排污许可证申请与核发技术规范 工业固体废物（试行）",
     "source": "…HJ 1200—2021…md",
     "text": "一般工业固体废物贮存应满足防渗漏、防雨淋、防扬尘要求。符合 GB 18599、GB 15562.2 和 HJ 2035 等标准。"},
    {"index": 2, "title": "一般工业固体废物贮存和填埋污染控制标准",
     "source": "…GB 18599-2020…md", "text": "贮存场应设置防扬散、防流失、防渗漏设施。"},
    {"index": 3, "title": "中华人民共和国固体废物污染环境防治法",
     "source": "…固废法…md", "text": "产生工业固体废物的单位应当采取措施防止污染。"},
]
for desc, ans, expect in [
    ("GB 18599 在资料里", "应符合 GB 18599 的要求。", False),
    ("破折号写法不同", "依据 HJ 1200-2021。", False),
    ("带年份且一致", "依据 HJ 1200—2021。", False),
    ("资料里的标准名", "依据《一般工业固体废物贮存和填埋污染控制标准》。", False),
    ("★张冠李戴 GB 30485", "符合 GB 18599、GB 30485 和 HJ 2035。", True),
    ("★年份不符 GB 18599—2023", "按 GB 18599—2023 执行。", True),
    ("编造编号 HJ 9999-2099", "按 HJ 9999-2099 执行。", True),
    ("编造文件名", "依据《固体废物现场检查技术指南》。", True),
    ("普通引号内容不误伤", "所谓《三防》即防扬散、防流失、防渗漏。", False),
    ("法名简称不误伤", "依据《固废法》。", False),
    ("省略「中华人民共和国」前缀", "依据《固体废物污染环境防治法》第四十条。", False),
    ("指南类文件应抓到", "依据《生活垃圾焚烧发电厂现场监督检查技术指南》。", True),
]:
    miss = mod.verify_citations(ans, SRC)
    ck(desc, bool(miss) == expect, f"命中={miss}")
runs = {tuple(mod.verify_citations("符合 GB 18599、GB 30485，按 GB 18599—2023 执行。", SRC)) for _ in range(50)}
ck("确定性（50 次一致）", len(runs) == 1, f"{len(runs)} 种结果")
ck("年份不符有专门说明", any("其它年份" in x for x in mod.verify_citations("按 GB 18599—2023 执行。", SRC)))
ck("无缺失不产生告警", mod.citation_warning([]) == "")
ck("告警含全部条目", "GB 30485" in mod.citation_warning(["GB 30485", "《A标准》"]))

# ============================================================
G("6. 分流判定 is_direct_chat / needs_context")
# ============================================================
for q, expect in [("好的", True), ("嗯", True), ("哈哈哈", True), ("在吗", True), ("谢谢", True),
                  ("五年", False), ("可以吗", False), ("危险废物转移联单几天内确认", False),
                  ("那要罚多少", False)]:
    ck(f"is_direct_chat({q!r}) = {expect}", mod.is_direct_chat(q) == expect)
ck("needs_context 指代词为真", mod.needs_context("那要怎么办") is True)
ck("needs_context 自包含为假", mod.needs_context("危险废物转移联单的确认期限是多久？") is False)

# ============================================================
G("7. 文本清洗 clean_retrieved_text / clean_general_answer / strip_think")
# ============================================================
t = mod.clean_retrieved_text(r"排放口 $(+)$）以及 ${\mathrm{BAF}}$ 与 \mathrm{abc} 说明")
ck("LaTeX 乱码被清掉", "$" not in t and "\\" not in t, repr(t))
ck("空括号被去掉", mod.clean_retrieved_text("排放口共6个（）") == "排放口共6个")
ck("免责尾段被删", "未提供" not in mod.clean_general_answer("正文内容。\n\n此外，未提供具体项目数据，因此无法判断。"))
ck("strip_think 取 </think> 之后", mod.strip_think("推理</think>正文") == "正文")
ck("strip_think 去分节前缀", mod.strip_think("【问题识别】内容") == "内容")

# ============================================================
G("8. 流式拆分器 ThinkAnswerSplitter")
# ============================================================
def feed_all(splitter, text, chunk=1):
    out = []
    for i in range(0, len(text), chunk):
        out += splitter.feed(text[i:i + chunk])
    out += splitter.flush()
    return out

for name, s in [("逐字符", 1), ("2 字符", 2), ("7 字符", 7), ("整体", 10 ** 6)]:
    ev = feed_all(mod.ThinkAnswerSplitter(), "<think>推理中</think>\n\n最终答案", s)
    r = "".join(x for t, x in ev if t == "reasoning")
    a = "".join(x for t, x in ev if t == "chunk")
    ck(f"[{name}] 推理与答案正确分离", "推理中" in r and a.strip() == "最终答案", f"r={r!r} a={a!r}")
ev = feed_all(mod.ThinkAnswerSplitter(), "<answer>你好</answer>", 3)
a = "".join(x for t, x in ev if t == "chunk")
r = "".join(x for t, x in ev if t == "reasoning")
ck("无 think 块时剥掉 <answer> 且正文进答案区", "<answer>" not in a and "你好" in a,
   f"a={a!r} r={r!r}")
ev = feed_all(mod.ThinkAnswerSplitter(), "【分析过程】想一下【回答】直接回答", 1)
a = "".join(x for t, x in ev if t == "chunk")
r = "".join(x for t, x in ev if t == "reasoning")
ck("无 think 块时【分析过程】/【回答】也正确分流",
   "直接回答" in a and "想一下" in r and "【回答】" not in a, f"a={a!r} r={r!r}")
ev = feed_all(mod.ThinkAnswerSplitter(), "<think>推理</think>\n\n答案", 2)
ck("有 think 块时行为不变（回归）",
   "".join(x for t, x in ev if t == "chunk").strip() == "答案")

# ★ 真实流形态：vLLM + enable_thinking 下模型**只输出收尾的 </think>**，
#   开头直接就是推理正文（实测原始 SSE 第一块 content='问题'，通篇没有 <think>）。
#   这一形态若判错，整段推理会被当成答案（第一版 KNOW-1 修法就是这样坏的）。
real = "问题问的是危险废物转移联单的确认期限。\n</think>\n\n确认期限为五个工作日。"
for name, s in [("逐字符", 1), ("3 字符", 3), ("13 字符", 13), ("整体", 10 ** 6)]:
    ev = feed_all(mod.ThinkAnswerSplitter(), real, s)
    a = "".join(x for t, x in ev if t == "chunk")
    r = "".join(x for t, x in ev if t == "reasoning")
    ck(f"[真实流/{name}] 推理进 reasoning、答案进 answer",
       "确认期限为五个工作日" in a and "问题问的是" in r and "</think>" not in a,
       f"r={r[:40]!r} a={a[:60]!r}")

# ============================================================
G("9. 历史规整 normalize_history")
# ============================================================
h = [{"role": "user", "content": "危险废物转移联单几天内确认？"},
     {"role": "assistant", "content": "五个工作日。"}]
ck("与当前问题完全相同的上一轮被去掉",
   mod.normalize_history(h, "危险废物转移联单几天内确认？") == [])
ck("无关历史被保留", len(mod.normalize_history(h, "排污许可证有效期是几年？")) == 2)

# ============================================================
G("10. HTTP 入口约束（TestClient，无模型调用）")
# ============================================================
try:
    from fastapi.testclient import TestClient
    client = TestClient(mod.app)
    ck("GET /health", client.get("/health").json().get("model") == mod.MODEL_NAME)
    html = client.get("/").text
    # ★ 这里只查"服务端返回的页面骨架里有这些元素"。
    # 原先还查 "md-table" —— 那是个 CSS 类名，拆模块后住在 app.css 里，
    # 不可能出现在 index.html 里（用备份实测确认过，拆模块前也不在）。
    # 它真正该被检查的地方是"整个 frontend/ 有没有这个样式"，
    # 见下面 P3 那一节的前端全目录检查。
    for token in ('id="fileInput"', 'id="photoMode"', 'id="imgViewer"', "attach-bar"):
        ck(f"页面含 {token}", token in html)
    # 页面引用的 CSS / JS 必须真的能取到 —— 这比在 HTML 里找类名有意义得多：
    # 拆模块后页面本体只有骨架，样式和行为都在外链文件里，外链 404 页面就是废的。
    for asset in ("/static/app.css", "/static/js/main.js"):
        ck(f"页面引用了 {asset}", asset in html, "index.html 里没有这个引用")
        _r = client.get(asset)
        ck(f"{asset} 能取到（{_r.status_code}）", _r.status_code == 200)
    # ★ 反向自测：不存在的静态资源必须 404，否则上面那条 200 说明不了什么
    ck("反向自测：不存在的资源 404",
       client.get("/static/zzz_不存在_zzz.css").status_code == 404)
    r = client.post("/hybrid_search/stream", json={"query": "", "history": []})
    ck("空请求（无文字无图）→ 400", r.status_code == 400, str(r.status_code))
    r = client.post("/hybrid_search", json={"query": "x", "image": "data:text/plain;base64,aGk="})
    ck("非图片 → 400", r.status_code == 400, str(r.status_code))
    r = client.post("/hybrid_search", json={"query": "x", "image": "data:image/png;base64," + "A" * (mod.MAX_IMAGE_CHARS + 10)})
    ck("超大图 → 413", r.status_code == 413, str(r.status_code))
    r = client.get("/hybrid_search")
    ck("GET /hybrid_search 缺 query → 422", r.status_code == 422, str(r.status_code))
    r = client.get("/kg/stats")
    ck("GET /kg/stats 可用", r.status_code == 200 and "nodes" in r.json())
    h = client.get("/health").json()
    ck("/health 回报密钥来源（env/missing）",
       h.get("intent_key_source") in ("env", "missing"), str(h))
    ck("/health 不含密钥本体", "sk-" not in json.dumps(h, ensure_ascii=False), str(h))
    r = client.get("/hybrid_search", params={"query": "危险废物转移联单期限", "report": "photo"})
    ck("GET + report=photo → 400（明确报错而非静默走偏）", r.status_code == 400, str(r.status_code))

    # ---- 原文 PDF 通路（P5）----
    hp = client.get("/health").json()
    ck("/health 回报 pdf_root", bool(hp.get("pdf_root")), str(hp))
    r = client.get("/doc", params={"source": "not_a_markdown.txt"})
    ck("/doc 非 .md 来源 → 400", r.status_code == 400, str(r.status_code))
    r = client.get("/doc", params={"source": "../../../etc/passwd.md"})
    ck("/doc 目录穿越 → 400", r.status_code == 400, str(r.status_code))
    r = client.get("/doc", params={"source": "生态环境标准规范/不存在的目录/不存在的文件.md"})
    ck("/doc 文件不存在 → 404", r.status_code == 404, str(r.status_code))

    # 用索引里真实存在的第一条来源验证"能取到 PDF"
    real_source = ""
    try:
        with open("/data/fagui_rag/index/chunks.jsonl", encoding="utf-8") as fh:
            for line in fh:
                real_source = json.loads(line).get("source", "")
                if real_source:
                    break
    except OSError:
        pass
    if real_source:
        r = client.get("/doc", params={"source": real_source})
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("application/pdf")
        if r.status_code == 404:
            ck(f"/doc 取真实原文 PDF（{real_source.split('/')[-1][:28]}…）", False,
               "PDF 还没上传到 pdf_root —— 先跑 push_tree.py")
        else:
            ck(f"/doc 取真实原文 PDF（前 4 字节={r.content[:4]!r}）", ok,
               f"HTTP {r.status_code} {r.headers.get('content-type')}")
        ck("/doc 返回内联预览而非下载",
           "inline" in (r.headers.get("content-disposition") or ""),
           str(r.headers.get("content-disposition")))
    else:
        print("  (跳过：读不到 /data/fagui_rag/index/chunks.jsonl)")
except ImportError:
    print("  (跳过：没有 fastapi.testclient)")

# ============================================================
if LIVE:
    G("11. 4 条路由事件形状（--live，真实调用）")
    import httpx
    import time

    def run(payload, timeout=600):
        ev = {"route": "", "chunks": 0, "reasoning": 0, "sources": 0, "vision": "", "error": "",
              "answer": "", "status": []}
        t0 = time.time()
        with httpx.stream("POST", f"{LIVE_BASE}/hybrid_search/stream",
                          json=payload, timeout=timeout) as r:
            if r.status_code != 200:
                ev["error"] = f"HTTP {r.status_code}"
                return ev
            e = d = None
            for line in r.iter_lines():
                s = line.strip()
                if s.startswith("event:"):
                    e = s[6:].strip()
                elif s.startswith("data:"):
                    d = s[5:].strip()
                elif s == "":
                    if not e:
                        continue
                    try:
                        p = json.loads(d) if d else None
                    except Exception:
                        p = None
                    if e == "chunk":
                        ev["chunks"] += 1
                        ev["answer"] += p if isinstance(p, str) else ""
                    elif e == "reasoning":
                        ev["reasoning"] += 1
                    elif e == "vision":
                        ev["vision"] = (p or {}).get("text", "")
                    elif e in ("meta", "done"):
                        ev["route"] = (p or {}).get("route", ev["route"])
                        ev["sources"] = len((p or {}).get("sources") or []) or ev["sources"]
                    elif e == "status":
                        ev["status"].append((p or {}).get("message"))
                    elif e == "error":
                        ev["error"] = p
                    e = d = None
        ev["elapsed"] = round(time.time() - t0, 1)
        return ev

    img = png_data_url("collected data table")
    # 每条用例声明"必须满足的条件"，失败的说明直接指出是哪一条不满足
    cases = [
        ("rag（纯文本专业）", {"query": "危险废物转移联单的确认期限是多久？", "history": []},
         {"route": "rag", "有引用": True}),
        ("general（纯文本科普）", {"query": "外卖餐盒算哪类垃圾？", "history": []},
         {"route": "general", "有引用": False}),
        # 图片内容决定路由：信息量小的图会走科普通道，所以只要求"有答案 + 路由合法 + 无错误"
        ("图片+文字", {"query": "这张图说明了什么？", "history": [], "image": img},
         {"route_in": ("rag", "general")}),
        ("只发图", {"query": "", "history": [], "image": img},
         {"route_in": ("rag", "general")}),
        ("photo 专业研判", {"query": "", "history": [], "image": img, "report": "photo"},
         {"route": "photo", "有引用": True,
          # 这张图信息量为零，模型可能两次都产不出合法 JSON → 走兜底分支。
          # 设计上必须"要么给结构化报告、要么明确告知结构化失败"，不允许静默给散文。
          "含核验清单或兜底提示": ("【三、核验清单】", "未能解析出结构化研判结果")}),
    ]
    for name, payload, expect in cases:
        ev = run(payload)
        problems = []
        if ev["error"]:
            problems.append(f"错误={ev['error']}")
        if not ev["answer"].strip():
            problems.append("答案为空")
        if "route" in expect and ev["route"] != expect["route"]:
            problems.append(f"路由应为 {expect['route']} 实为 {ev['route'] or '-'}")
        if "route_in" in expect and ev["route"] not in expect["route_in"]:
            problems.append(f"路由 {ev['route'] or '-'} 不在 {expect['route_in']}")
        if "有引用" in expect and expect["有引用"] and ev["sources"] <= 0:
            problems.append("应有引用但为 0")
        if "有引用" in expect and not expect["有引用"] and ev["sources"] != 0:
            problems.append(f"不应有引用却有 {ev['sources']} 条")
        if "含核验清单" in expect and expect["含核验清单"] not in ev["answer"]:
            problems.append("缺少核验清单")
        if "含核验清单或兜底提示" in expect and not any(
                t in ev["answer"] for t in expect["含核验清单或兜底提示"]):
            problems.append("既没有结构化报告、也没有兜底提示（静默降级）")
        ck(f"{name} → route={ev['route'] or '-'} 引用={ev['sources']} "
           f"reasoning={ev['reasoning']}块 chunk={ev['chunks']}块 {ev.get('elapsed')}s 答案={len(ev['answer'])}字",
           not problems, "；".join(problems))

    # P2 的核心承诺：流式与非流式共用同一条事件流，因此必须一致
    G("11b. 流式 / 非流式一致性（同一事件流）")
    for label, payload in [
        ("rag", {"query": "危险废物转移联单的确认期限是多久？", "history": []}),
        ("general", {"query": "外卖餐盒算哪类垃圾？", "history": []}),
    ]:
        st = run(payload)
        nr = httpx.post(f"{LIVE_BASE}/hybrid_search", json=payload, timeout=600)
        problems = []
        if nr.status_code != 200:
            problems.append(f"非流式 HTTP {nr.status_code}")
            j = {}
        else:
            j = nr.json()
            if j.get("route") != st["route"]:
                problems.append(f"路由不一致 流式={st['route']} 非流式={j.get('route')}")
            if len(j.get("sources") or []) != st["sources"]:
                problems.append(f"引用数不一致 流式={st['sources']} 非流式={len(j.get('sources') or [])}")
            if not (j.get("answer") or "").strip():
                problems.append("非流式答案为空")
            if not (j.get("reasoning") or "").strip():
                problems.append("非流式推理为空")
            if not j.get("usage"):
                problems.append("非流式 usage 为空（说明流式 usage 收集没生效）")
        ck(f"{label}：流式与非流式一致（路由/引用/答案/推理/usage）", not problems, "；".join(problems))
        if not problems:
            print(f"     流式 route={st['route']} 引用={st['sources']} {st['elapsed']}s ｜ "
                  f"非流式 route={j.get('route')} 引用={len(j.get('sources') or [])} "
                  f"usage={j.get('usage')}")

# ============================================================
G("12. P2 结构约束：4 条路由只能有一份实现（仅包结构）")
# ============================================================
if os.path.isdir(SITE):
    import glob
    pkg_dir = os.path.dirname(os.path.abspath(mod.__file__))
    srcs = {os.path.basename(p): open(p, encoding="utf-8").read()
            for p in glob.glob(os.path.join(pkg_dir, "*.py"))}
    all_src = "".join(srcs.values())

    ck("存在 run_pipeline（唯一编排）", hasattr(mod, "run_pipeline"))
    ck("run_pipeline 是异步生成器",
       hasattr(mod.run_pipeline, "__call__") and mod.run_pipeline.__code__.co_flags & 0x200 != 0
       if hasattr(mod, "run_pipeline") else False)
    for label, needle in [
        ("direct_chat 提示词", "对问候、身份、自我介绍和功能类问题直接、简洁、自然地回答"),
        ("RAG 提示词", "你是悉数清宇大模型，负责生态环境法律法规、标准规范和监管执法问答"),
        ("photo 契约", "这是图片信息抽取任务" if False else "请对上面这张现场照片"),
    ]:
        cnt = all_src.count(needle)
        ck(f"{label}在包内只出现 1 次（去重生效）", cnt == 1, f"出现 {cnt} 次")
    ck("routes.py 不再自己调模型（编排已移出）",
       "stream_model(" not in srcs.get("routes.py", "") and "call_model(" not in srcs.get("routes.py", ""))
    ck("routes.py 不再做意图分流（is_direct_chat 已移出）",
       "is_direct_chat" not in srcs.get("routes.py", ""))
    ck("非流式端点复用 answer_query",
       "answer_query(request)" in srcs.get("routes.py", ""))
    ck("流式端点复用 run_pipeline",
       "run_pipeline(" in srcs.get("routes.py", ""))

    # ---- P3：前端外置 + 密钥走环境变量 ----
    #
    # ★ 2026-09-18 修检查器本身（不是放宽标准）。
    #
    # 前端在"阶段 2b 拆模块"时把 CSS 迁到 app.css、JS 迁到 js/*.js，
    # index.html 从 4 万多字符缩到 5.8K。而下面几条断言仍然只在 index.html
    # 里找 md-table / pdf-link、仍然要求 index.html 本身体积 >20KB ——
    # 它们**从拆模块那天起就失效了**，一直红着，于是真正的回归信号被淹没。
    #
    # 用备份文件实测确认过：md-table 和 pdf-link 在改动前的 index.html 里
    # 同样不存在（现在在 app.css 和 js/message.js 里），5805 字符同样 <20000。
    # 所以这几条不是本次改动弄坏的。
    #
    # 修法：断言要编码的**不变量**没变（前端得有 markdown 表格样式、
    # 得有"查看原文"入口、整页 HTML 不在 routes.py 里），变的是这些东西
    # 现在住在哪 —— 所以改成在整个 frontend/ 目录里找，而不是死盯 index.html。
    FE_DIR = os.path.join(SITE, "frontend")
    fe = os.path.join(FE_DIR, "index.html")
    ck("frontend/index.html 存在", os.path.isfile(fe), fe)
    if os.path.isfile(fe):
        html = open(fe, encoding="utf-8").read()
        # 页面骨架必须在 index.html 里
        for token in ('id="fileInput"', 'id="photoMode"', "<!doctype html>"):
            ck(f"index.html 含 {token}", token in html)
        # 样式与行为可以在 CSS/JS 模块里 —— 全目录搜
        _fe_all = {}
        for _root, _dirs, _files in os.walk(FE_DIR):
            for _f in _files:
                if _f.endswith((".html", ".css", ".js")):
                    _p = os.path.join(_root, _f)
                    try:
                        _fe_all[os.path.relpath(_p, FE_DIR)] = open(_p, encoding="utf-8").read()
                    except Exception:
                        pass
        _joined = "\n".join(_fe_all.values())
        ck("前端（html+css+js）文件收集非空", len(_fe_all) >= 5,
           f"收集到 {len(_fe_all)} 个文件")
        for token in ("md-table", "attach-bar", "pdf-link"):
            _where = [p for p, t in _fe_all.items() if token in t]
            ck(f"前端整体含 {token}", bool(_where),
               f"出现在 {_where}" if _where else "全目录都没找到")
        # ★ 反向自测：确保上面的"全目录搜"真的在搜东西 ——
        #   拿一个绝不可能存在的 token 去搜，必须搜不到。
        #   不加这一条的话，"搜到了"可能只是因为搜索逻辑永远返回真。
        _ghost = [p for p, t in _fe_all.items() if "zzz_这个token绝对不存在_zzz" in t]
        ck("反向自测：不存在的 token 搜不到（说明搜索有效）", not _ghost, f"{_ghost}")
        ck("routes.py 里不再有整页 HTML（外置生效）",
           "<style>" not in srcs.get("routes.py", "") and "<!doctype" not in srcs.get("routes.py", ""))
        ck("index() 从文件读取", "FRONTEND_PATH" in srcs.get("routes.py", ""))
        # 前端体积：看**整个 frontend/** 而不是只看 index.html。
        # 拆模块后 index.html 只有 5.8K 是设计使然（骨架），
        # 样式在 app.css、行为在 js/*.js。总量才是"有没有把前端丢了"的信号。
        _total = sum(len(t) for t in _fe_all.values())
        ck("前端总体积合理（html+css+js > 20KB）", _total > 20000, f"{_total} 字符")
    cfg = srcs.get("config.py", "")
    ck("密钥优先读环境变量", "os.environ.get(\"INTENT_API_KEY\")" in cfg or "INTENT_API_KEY" in cfg)
    ck("密钥来源可观测", "INTENT_KEY_SOURCE" in cfg)
    ck(".env 加载器存在（launcher 不用改）", "_load_dotenv" in cfg)
    # ★ 代码里不得残留任何密钥明文（P3 的验收点）
    leaked = [os.path.basename(p) for p, s in srcs.items() if "sk-" in s]
    ck("包内代码不含密钥明文", not leaked, f"出现在 {leaked}")
    # ★ 原来这条是 `routes.py < 200 行`，用行数当"HTML 已外置"的替身指标。
    # 改动前 routes.py 就已经 308 行（加了统一错误码契约与三个异常处理器），
    # 现在 397 行（又加了 /doc/info、/doc/text 与 /cache/stats）。
    # 行数早已不能代表"里面有没有整页 HTML" —— 上一行那条
    # "routes.py 里不再有整页 HTML" 才是**直接**检查，它一直是绿的。
    # 所以改成直接查标记：routes.py 里不许出现页面标签。
    # 同时保留一个宽松上限，防止哪天有人把整页 HTML 又贴回来。
    _rt = open(os.path.join(pkg_dir, "routes.py"), encoding="utf-8").read()
    _markup = [m for m in ("<!doctype", "<html", "<style>", "<body", "<div class=")
               if m in _rt.lower()]
    ck("routes.py 不含页面标记（HTML 确实外置）", not _markup, f"发现 {_markup}")
    ck("routes.py 行数在合理范围（<800）",
       _rt.count("\n") + 1 < 800, f"{_rt.count(chr(10)) + 1} 行")
    # ★ 反向自测：上面那个标记检查必须真的能发现页面标签 ——
    #   否则把 _markup 写死成 [] 也能通过。
    _fake = "<!doctype html><html><body><div class=\"x\">"
    _fake_hit = [m for m in ("<!doctype", "<html", "<style>", "<body", "<div class=")
                 if m in _fake.lower()]
    ck("反向自测：页面标记检查有效", len(_fake_hit) >= 4, f"命中 {_fake_hit}")
    # ---- 原文 PDF 通路（P5）----
    rt = srcs.get("routes.py", "")
    ck("routes.py 有 /doc 路由", '"/doc"' in rt)
    ck("/doc 做了路径越界检查", "not in target.parents" in rt)
    ck("/doc 用内联预览", 'content_disposition_type="inline"' in rt)
    ck("索引元数据已透传（standard_id）", '"standard_id"' in srcs.get("retrieve.py", ""))
    if os.path.isfile(fe):
        # 「查看原文」入口已在上面的前端全目录检查里覆盖（pdf-link 现在住在
        # app.css / js/message.js）。这里不再重复查 index.html。
        pass
else:
    print("  (跳过：单文件形态没有包结构约束)")

print("\n" + "=" * 60)
if known:
    print(f"已知遗留（测试正确、代码待修，不计入失败）：{len(known)} 项")
    for k in known:
        print("   ⚠️", k)
print("全部通过 ✅" if not fails else f"失败 {len(fails)} 项：")
for f in fails:
    print("   -", f)
sys.exit(0 if not fails else 1)
