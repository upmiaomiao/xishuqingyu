#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告生成智能体 · 网页路由（挂进现有 8011 站点，不新起服务）。

照 audit_routes.py 的路子：包内新增模块 + routes.py 挂载，启动命令/端口/环境变量一律不动
（启动脚本 md5 冻结，不得改动）。

生成是**长任务**（判定+渲染+自审，带模型叙述时要调模型），所以：
  · POST /gen/api/run 立即返回 job_id，后台线程跑；
  · GET  /gen/api/job/{id} 轮询进度与结果（校验/判定/生成/自审四段输出都回传）；
  · GET  /gen/api/download/{id} 取生成的 .docx。

与审核页共用同一套判据（引擎判据在 /data/fagui_rag/criteria，生成侧结构/标准清单在
/data/eia_report_gen/判据库）。生成侧的判定层**调用审核侧同一函数**，所以两边不会打架。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
import traceback
import uuid

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from .errors import ApiError

router = APIRouter(prefix="/gen", tags=["gen"])

GEN_HOME = os.environ.get("GEN_HOME", "/data/eia_report_gen")
AUDIT_HOME = os.environ.get("AUDIT_HOME", "/data/eia_audit")
# 生成侧模块在 import 时读这两个环境变量决定判据/审核包位置 → 必须在导入 gen 之前设好
os.environ.setdefault("GEN_HOME", GEN_HOME)
os.environ.setdefault("AUDIT_HOME", AUDIT_HOME)
if GEN_HOME not in sys.path:
    sys.path.insert(0, GEN_HOME)
if AUDIT_HOME not in sys.path:
    sys.path.insert(0, AUDIT_HOME)

_JOBS: dict = {}
_LOCK = threading.Lock()

# 四个阶段。为什么用固定档位而不是按时间估算：
# 各阶段耗时完全不成比例（①校验/②判定是纯代码、毫秒级，③生成要调模型、占九成时间），
# 按时间估出来的数字会一直"骗人"。
#
# 档位的含义是**「走到这一步时，前面已经完成了几步」**，不是"还剩多久"：
#   ①校验 跑起来 → 5%（刚开始）   ③生成 跑起来 → 35%（前两步已完，最大一块活刚开始）
#   ②判定 跑起来 → 18%            ④自审 跑起来 → 85%（正文已出，在回灌审核）
# 所以第一版给的 65% 是错的 —— ③生成 一开始就显示 65%，用户会以为快好了，
# 实际最大的那块活才刚开始。界面同时显示"第 N/4 步"与走动秒表，
# 秒表才是真正诚实的那个信号。
STAGES = ("①校验", "②判定", "③生成", "④自审")
STAGE_PCT = {"①校验": 5, "②判定": 18, "③生成": 35, "④自审": 85}
_PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "frontend", "gen.html")
OUT_DIR = os.path.join(GEN_HOME, "_生成结果")
ARCHIVE_DIR = os.path.join(OUT_DIR, "_已归档")     # 归档目录：放在 OUT_DIR 下，列表只扫 *.docx 所以不会显示出来
SAMPLE_DIR = os.path.join(GEN_HOME, "样例")
# 批量删除的备份目录前缀：`_生成结果/_已删除_<时间戳>/`。列表只扫 *.docx，目录不会显示出来。
TRASH_PREFIX = "_已删除_"
TRASH_KEEP = int(os.environ.get("GEN_TRASH_KEEP", "5"))   # 只留最近 5 批，免得越堆越多


def _engine():
    """延迟导入：生成引擎缺依赖时不能连累整个 8011 站点。"""
    from gen import decide, docx_writer, schema, selfaudit
    return decide, docx_writer, schema, selfaudit


def _intake():
    from gen import intake
    return intake


# ---------------------------------------------------------------- 对话式填报

_SESS: dict = {}


def _sess(sid: str) -> dict:
    s = _SESS.get(sid)
    if not s:
        raise ApiError('E_SESSION_NOT_FOUND', "会话不存在或已过期，请重新开始")
    return s


def _sess_view(s: dict) -> dict:
    """给页面看的会话状态：已知什么、依据是什么、被丢弃了什么、下一个问题。"""
    try:
        intake = _intake()
        g = intake.gaps(s["data"], max_ask=6)
        qs = intake.phrase_questions(g["要问"])
    except Exception as exc:                                      # noqa: BLE001
        g, qs = {"还剩": 0, "缺项总数": 0, "剩余项": []}, []
        s["问答"].append({"问题": "（问题生成失败）", "答": str(exc), "类型": "error"})
    return {"session": s["id"], "已知": intake_summary(s["data"]), "依据": s.get("依据") or {},
            "丢弃": (s.get("丢弃") or [])[-12:], "问题": qs, "还剩": g.get("还剩", 0),
            "缺项总数": g.get("缺项总数", 0), "剩余项": g.get("剩余项") or [],
            "对话": s["问答"], "描述": s.get("描述") or ""}


def intake_summary(data: dict) -> list:
    """已知事实的可读列表（含每条的原文依据）。"""
    ks = {}
    try:
        from gen import schema
        ks = schema.by_key()
    except Exception:                                             # noqa: BLE001
        pass
    rows = []
    for k, v in data.items():
        if k == "补充事实":
            for t in (v or []):
                rows.append({"字段": "补充事实：" + str(t.get("名称")),
                             "值": ("不适用（明确否定）" if t.get("不适用") else t.get("值"))})
            continue
        f = ks.get(k)
        rows.append({"字段": (f.name if f else k),
                     "值": v if isinstance(v, (str, int, float, bool))
                     else json.dumps(v, ensure_ascii=False)[:80]})
    return rows


@router.post("/api/chat/start")
async def api_chat_start(request: Request) -> dict:
    """用户用自然语言说项目 → 抽取事实（代码核验依据）→ 生成要问的问题。"""
    body = await request.json()
    text = (body.get("text") or "").strip()
    if len(text) < 8:
        raise ApiError('E_BAD_REQUEST', "请把项目情况多写几句（至少一句完整的话）")
    intake = _intake()
    r = intake.parse_description(text)
    old = _SESS.get(body.get("session") or "")
    sid = old["id"] if old else uuid.uuid4().hex[:12]
    if old:
        # 补充描述：只**填补空缺**，已确认过的不覆盖（用户先说后改，得由用户明确说改，
        # 不能因为第二段话的措辞不同就把已确认的值冲掉）。冲突逐条记下。
        merged, conflicts = dict(old["data"]), []
        for k, v in r["采纳"].items():
            if merged.get(k) in (None, "", []):
                merged[k] = v
                (old.setdefault("依据", {}))[k] = (r.get("依据") or {}).get(k, "")
            elif merged.get(k) != v:
                conflicts.append({"字段": k, "值": json.dumps(v, ensure_ascii=False)[:60],
                                  "原因": "已有值 %s，未覆盖（如要更正请在问题里回答）"
                                          % json.dumps(merged[k], ensure_ascii=False)[:40]})
        s = old
        s["data"] = merged
        s["丢弃"] = (s.get("丢弃") or []) + (r.get("丢弃") or []) + conflicts
        s["描述"] = (s.get("描述") or "") + "\n" + text
    else:
        s = {"id": sid, "data": dict(r["采纳"]), "依据": r.get("依据") or {},
             "丢弃": r.get("丢弃") or [], "问答": [], "描述": text,
             "created": time.strftime("%H:%M:%S")}
        _SESS[sid] = s
    out = _sess_view(s)
    out["采纳数"] = len(r["采纳"])
    out["丢弃数"] = len(r["丢弃"]) + (len(conflicts) if old else 0)
    return {"ok": True, **out}


@router.post("/api/chat/answer")
async def api_chat_answer(request: Request) -> dict:
    """用户自由文本回答一个问题（可答"不知道"，那就留空不填）。"""
    body = await request.json()
    s = _sess(body.get("session") or "")
    intake = _intake()
    item = {"key": body.get("key"), "中文名": body.get("中文名") or "",
            "类型": body.get("类型") or "str", "事实名": body.get("事实名")}
    r = intake.apply_answer(s["data"], item, body.get("text") or "")
    s["data"] = r["data"]
    s["问答"].append({"问题": body.get("问题") or item["中文名"], "答": body.get("text") or "",
                      "结果": r["说明"], "采纳": r["采纳"]})
    if not r["采纳"] and body.get("text"):
        s["丢弃"] = (s.get("丢弃") or []) + [{"字段": item["中文名"] or item["key"],
                                              "值": (body.get("text") or "")[:40],
                                              "原因": r["说明"]}]
    out = _sess_view(s)
    out["本次"] = r["说明"]
    out["采纳"] = r["采纳"]
    return {"ok": True, **out}


@router.post("/api/chat/skip")
async def api_chat_skip(request: Request) -> dict:
    """跳过一个问题（记进对话，明确留空）。"""
    body = await request.json()
    s = _sess(body.get("session") or "")
    s["问答"].append({"问题": body.get("问题") or body.get("中文名") or "",
                      "答": "（跳过）", "结果": "未提供，草稿里会标【需人工补充】", "采纳": False})
    return {"ok": True, **_sess_view(s)}


@router.get("/api/chat/state/{sid}")
async def api_chat_state(sid: str) -> dict:
    return {"ok": True, **_sess_view(_sess(sid))}


@router.post("/api/chat/reset")
async def api_chat_reset(request: Request) -> dict:
    """丢掉这一次会话（页面点「新建报告」）。

    只清内存里的会话状态：**已经生成的 Word 文件一个都不删**（归档不删是原则，
    那些稿子仍能在「历史报告」里预览/下载）。会话不清理会一直堆在内存里，
    重启就全丢 —— 顺手在"新建"时释放。
    """
    body = await request.json()
    sid = body.get("session") or ""
    with _LOCK:
        had = _SESS.pop(sid, None)
    return {"ok": True, "已清理": bool(had), "会话": sid[:8]}


@router.get("/api/chat/demo")
async def api_chat_demo(exclude: str = "") -> dict:
    """给页面一个"照着说"的示例描述（虚构项目，已标明）。

    **每次点都换一条**：示例是手写的几条虚构项目（不同行业、不同敏感目标），
    轮着给；同一个示例不会连着出现两次（exclude 传上一次给的文本）。
    这样"换个示例 → 生成"能真的产出一份不同的报告，便于看出正文是按事实生成的。
    """
    global _DEMO_IDX
    with _LOCK:
        n = len(DEMO_TEXTS)
        start = _DEMO_IDX % n
        pick = start
        for k in range(n):                       # 跳过和上一次相同的那条
            if exclude and DEMO_TEXTS[(start + k) % n].strip() == exclude.strip():
                pick = (start + k + 1) % n
                continue
            pick = (start + k) % n
            break
        _DEMO_IDX = (pick + 1) % n
    return {"ok": True, "示例": DEMO_TEXTS[pick], "序号": pick + 1, "总数": n,
            "说明": "这是虚构示例，只为演示对话流程；不要当成真实项目。"}


# DEMO_TEXTS 定义在下面 DEMO_TEXT 之后（它引用 DEMO_TEXT，放前面导入就会 NameError）


DEMO_TEXT = (
    "【虚构示例】我们公司要在临沂市兰山区汪沟镇建一台 20 吨/小时的生物质锅炉，"
    "给现有生产线供蒸汽，属于技术改造项目。总投资 1200 万元，其中环保投资 85 万元，"
    "用地面积 3000 平方米。锅炉配布袋除尘和双碱法脱硫，烟气经 25 米高排气筒排放。"
    "厂界东北方向 320 米有阳光村，约 120 户 480 人。生产废水不外排，"
    "全部沉淀后回用于除尘，不新增河道取水。项目还没有开工建设。"
)

# 手写的虚构示例（不同行业/规模/敏感目标）。**故意不给项目名称**，
# 好让"项目名称"这个问题在第一轮就被问到 —— 这本身也是演示的一部分。
# 必须放在 DEMO_TEXT 之后（第一版放在前面，导入时就 NameError）。
DEMO_TEXTS = [
    DEMO_TEXT,
    ("【虚构示例】某机械加工厂新增 8 台数控机床和 2 台加工中心，年加工金属件 5000 吨，"
     "总投资 800 万元，其中环保投资 30 万元，用地面积 2000 平方米。切削液循环使用不外排，"
     "金属废屑外售综合利用；焊接工序配移动式集气罩+布袋除尘器，15 米排气筒排放。"
     "厂界南侧 150 米是李家村约 60 户 210 人。项目尚未开工建设。"),
    ("【虚构示例】某加油站迁建项目，设 4 个 30 立方米埋地卧式双层油罐（2 汽 2 柴），"
     "6 台加油机，年销售汽油 3000 吨、柴油 2000 吨，总投资 600 万元，环保投资 45 万元，"
     "用地 1500 平方米。卸油和加油设油气回收系统，储罐区做防渗；"
     "洗车废水经隔油沉淀后循环使用不外排，生活污水排入市政污水管网。"
     "站址东侧 80 米为现状道路，南侧 260 米是王家疃村约 90 户 300 人。"),
    ("【虚构示例】某生猪养殖场建设项目，年出栏生猪 12000 头，占地 45 亩，"
     "总投资 1800 万元，环保投资 160 万元。粪污采用干清粪工艺，"
     "粪便堆肥外售，污水经黑膜沼气池厌氧处理后全部用于周边农田灌溉，不外排；"
     "场区恶臭采取喷洒除臭剂+绿化隔离。场界西侧 400 米有赵家庄约 70 户 240 人，"
     "北侧 900 米为一条小河。项目正在办理前期手续，尚未开工。"),
    ("【虚构示例】某工业园区污水处理厂提标改造工程，处理规模由 1 万吨/日提至 2 万吨/日，"
     "总投资 5600 万元，环保投资 5600 万元，用地 12000 平方米。"
     "工艺在原 A²/O 后增设高效沉淀池+反硝化滤池，尾水由一级 B 提标至一级 A 后排入沙河；"
     "污泥脱水至 60% 含水率后外运焚烧。排放口下游 2 公里内无饮用水水源保护区，"
     "厂界北侧 120 米为园区内现有企业。"),
]
_DEMO_IDX = 0


@router.post("/api/chat/generate")
async def api_chat_generate(request: Request) -> dict:
    """把对话里收集到的事实交给生成管线（缺项不拦，草稿里标注）。"""
    body = await request.json()
    s = _sess(body.get("session") or "")
    data = dict(s["data"])
    if not data:
        raise ApiError('E_BAD_REQUEST', "还没有收集到任何项目信息")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "status": "queued", "log": [],
                         "项目名称": data.get("项目名称") or "（未命名）",
                         "created": time.strftime("%H:%M:%S"), "session": s["id"],
                         "t0": time.time(), "pct": 4}
    threading.Thread(target=_run_job, args=(job_id, data, bool(body.get("model", True)),
                                            False, s.get("依据") or {},
                                            bool(body.get("fresh", False))), daemon=True).start()
    return {"ok": True, "job": job_id}


@router.get("/api/preview/{job_id}", response_class=HTMLResponse)
async def api_preview(job_id: str) -> HTMLResponse:
    """整份报告预览 —— 直接渲染**交付件本身**，不另写一套渲染（避免预览与 Word 不一致）。"""
    with _LOCK:
        j = _JOBS.get(job_id)
    if not j or not j.get("file"):
        raise ApiError('E_NO_ARTIFACT', "该任务还没有产物可预览")
    p = os.path.join(OUT_DIR, j["file"])
    if not os.path.isfile(p):
        raise ApiError('E_FILE_NOT_FOUND', "产物已不在磁盘上")
    from gen import preview as _p
    title = (j.get("项目名称") or "") + " 环境影响报告表（草稿）"
    return HTMLResponse(_p.docx_to_html(p, title))


@router.get("/api/preview_file/{name}", response_class=HTMLResponse)
async def api_preview_file(name: str) -> HTMLResponse:
    p = os.path.join(OUT_DIR, os.path.basename(name))
    if not os.path.isfile(p):
        raise ApiError('E_FILE_NOT_FOUND', "没有这个文件")
    from gen import preview as _p
    return HTMLResponse(_p.docx_to_html(p, os.path.basename(name)))


def _samples() -> list:
    if not os.path.isdir(SAMPLE_DIR):
        return []
    out = []
    for n in sorted(os.listdir(SAMPLE_DIR)):
        if n.endswith(".json"):
            p = os.path.join(SAMPLE_DIR, n)
            out.append({"name": n, "size": os.path.getsize(p)})
    return out


def _run_job(job_id: str, data: dict, use_model: bool, strict: bool = True,
             evidence: dict = None, fresh: bool = False) -> None:
    """后台跑四步：①校验 ②判定 ③生成 ④自审。每一步的结论都回传前端。

    strict=False 用于**对话式**生成：用户在聊天里可能有几项确实不知道，
    这时不拦着生成，而是把缺项在草稿里标【需人工补充】（类型错误照旧拦）。
    evidence 是对话里每条事实的原文依据，写进生成说明便于复核。
    fresh=True 是用户点"重新生成（换一版措辞）"：跳过叙述缓存、温度抬到 0.6，
    所以措辞会变，但**不再保证同输入同字节**（默认路径仍然字节可复现）。
    """
    def log(step, text, level="info"):
        with _LOCK:
            _JOBS[job_id]["log"].append({"step": step, "text": text, "level": level,
                                         "t": round(time.time(), 1)})
            # 顺带把"当前阶段 + 进度"也写进任务，让前端能像审核链路那样显示
            # 进度条与已用秒数（原先只有日志行，用户得自己数行猜进度）。
            _JOBS[job_id]["stage"] = step
            _JOBS[job_id]["pct"] = STAGE_PCT.get(step, _JOBS[job_id].get("pct") or 4)
            _JOBS[job_id]["step"] = (STAGES.index(step) + 1) if step in STAGES else None

    try:
        decide, docx_writer, schema, selfaudit = _engine()
    except Exception as exc:                                      # noqa: BLE001
        with _LOCK:
            _JOBS[job_id].update(status="failed", error=f"生成引擎不可用：{exc}",
                                 trace=traceback.format_exc()[-1500:])
        return
    try:
        with _LOCK:
            _JOBS[job_id]["status"] = "running"

        # ① 校验
        log("①校验", "校验收集到的项目信息")
        v = schema.validate(data, strict=strict)
        log("①校验", "已填 %d / %d 字段" % (v["已填字段数"], v["字段总数"]))
        if not v["ok"]:
            for e in v["errors"]:
                log("①校验", e, "error")
            log("①校验", "**校验未通过，不生成**（缺什么就列什么，工具不替人默认）", "error")
            with _LOCK:
                _JOBS[job_id].update(status="rejected", 校验=v)
            return
        if v["missing_required"]:
            log("①校验", "未提供 %d 项必填，草稿里会逐项标【需人工补充】：%s"
                % (len(v["missing_required"]),
                   "、".join(x.split("（")[0] for x in v["missing_required"][:10])), "warn")
        log("①校验", "校验通过", "ok")
        if v["warnings"]:
            log("①校验", "选填未填 %d 项，将留【需人工补充】：%s"
                % (len(v["warnings"]), "、".join(v["warnings"][:8])), "warn")

        # ② 判定
        log("②判定", "名录档级 / 专项评价 / 章节清单（纯代码，依据可查）")
        dec = decide.decide(data)
        c = dec["名录"]
        log("②判定", "名录档级：%s%s" % (c.get("tier") or "未定",
                                     "" if c.get("decided") else
                                     "（倾向 %s，事实不足）" % (c.get("倾向档位") or "?")), "ok")
        log("②判定", "命中条目：序号%s %s" % (c.get("名录序号"), c.get("名录条目")))
        for x in dict.fromkeys(c.get("待补事实") or []):
            log("②判定", "为定档需补的事实（照条件原文填「补充事实」）：%s" % x, "warn")
        for r in dec["专项评价"]["要素"]:
            if r.get("set_special") is True or r.get("status") == "unknown":
                log("②判定", "专项评价 %s：%s —— %s"
                    % (r["element"], {True: "应设", False: "不设", None: "未定"}[r.get("set_special")],
                       (r.get("reason") or "")[:80]),
                    "warn" if r.get("set_special") is None else "info")
        log("②判定", "章节清单 %d 节（来源：判据库/报告表结构.json）" % len(dec["章节"]))
        log("②判定", "标准候选 %d 个（语料共现，须人工核定）" % len(dec["标准"]["候选"]))
        # C6（用户反馈「生成过程看不到当前判定，希望有个判定摘要卡片」）：
        # 判定在②就做完了，但原先只在 status=done 时才把 判定 塞进任务里，
        # 于是生成过程中（③要调模型、耗时最长）前端拿不到任何判定信息。
        # 这里**判定一出来就回传**，轮询接口原样透传 dict(job)，前端据此渲染只读卡片。
        with _LOCK:
            _JOBS[job_id]["判定"] = dec_summary(dec)

        # ③ 生成（可选模型叙述）
        narration = None
        if use_model:
            from gen import narrate
            log("③生成", "调用模型写叙述（受出处闸门约束：含数字的句子必须能在事实表里找到出处）")
            if fresh:
                log("③生成", "重新生成：跳过叙述缓存、温度 0.6 —— 措辞会变，"
                             "因此这一版不保证与上次字节一致（默认路径仍可复现）", "warn")
            narration = narrate.narrate(data, dec, fresh=fresh)
            drop = sum(len(x["剔除"]) for x in narration["小节"].values())
            log("③生成", "事实表 %d 条；叙述 %d 小节；被出处闸门剔除 %d 句"
                % (len(narration["事实表"]), len(narration["小节"]), drop),
                "warn" if drop else "ok")
            for x in narration["小节"].values():
                for d in x["剔除"]:
                    log("③生成", "剔除：%s → %s" % (d["句"][:60], d["原因"][:70]), "warn")
        name = (data.get("项目名称") or "未命名项目").replace("/", "_").replace("\\", "_")
        stamp = time.strftime("%Y%m%d-%H%M%S")
        out = os.path.join(OUT_DIR, "%s-报告表草稿-%s.docx" % (name, stamp))
        docx_writer.build(data, dec, out, narration=narration,
                          evidence=evidence if strict is False else None)
        log("③生成", "已生成：%s（%d 字节）" % (os.path.basename(out), os.path.getsize(out)), "ok")

        # ④ 自审
        log("④自审", "把生成的稿子回灌审核引擎 18 项")
        res = selfaudit.audit_draft(out)
        log("④自审", "适用 %d 项，结论分布：%s" % (res["适用项数"], res["分布"]),
            "warn" if res["分布"].get("存在疑似问题") else "ok")
        for it in res["需注意"]:
            log("④自审", "[%s] %s：%s" % (it["状态"], it["审核项"], (it.get("理由") or "")[:110]),
                "warn")
        log("④自审", res["说明"])

        with _LOCK:
            _JOBS[job_id].update(status="done", 校验=v, 判定=dec_summary(dec),
                                 自审={"适用项数": res["适用项数"], "分布": res["分布"],
                                       "需注意": res["需注意"]},
                                 file=os.path.basename(out), size=os.path.getsize(out),
                                 模型=bool(use_model))
    except Exception as exc:                                      # noqa: BLE001
        with _LOCK:
            _JOBS[job_id].update(status="failed", error="%s: %s" % (type(exc).__name__, exc),
                                 trace=traceback.format_exc()[-2000:])
        log("错误", "%s: %s" % (type(exc).__name__, exc), "error")


def dec_summary(dec: dict) -> dict:
    """判定结果里可 JSON 化的部分（判据对象不进 JSON）。"""
    return {
        "名录": {k: v for k, v in dec["名录"].items()
                 if isinstance(v, (str, int, float, bool, list, type(None)))},
        "专项评价": {"要素": dec["专项评价"]["要素"],
                     "数量上限": {k: v for k, v in dec["专项评价"]["数量上限"].items()
                                  if k != "判据原文"},
                     "冲突": dec["专项评价"].get("冲突") or []},
        "章节": [{"序号": s["序号"], "名称": s["名称"], "表": s.get("表"),
                  "字段数": len(s["字段"]),
                  "已填字段": sum(1 for f in s["字段"] if f["已填"])} for s in dec["章节"]],
        "标准候选": dec["标准"]["候选"],
        "标准已排除": dec["标准"]["已排除"],
        "危险物质": dec["危险物质"],
        "需人工确认": dec["需人工确认"],
    }


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def page() -> HTMLResponse:
    if not os.path.isfile(_PAGE):
        raise ApiError('E_FRONTEND_MISSING', "缺少前端页 frontend/gen.html")
    with open(_PAGE, encoding="utf-8") as f:
        return HTMLResponse(f.read())


@router.get("/static/{fname}")
async def gen_static(fname: str):
    """静态资源与审核页同一套做法：走路由前缀，便于缓存控制与灰度。"""
    ok = {"gen_ui.css": "text/css; charset=utf-8",
          "gen_ui.js": "application/javascript; charset=utf-8"}
    if fname not in ok:
        raise ApiError('E_RESOURCE_MISSING', "静态资源不存在")
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", fname)
    if not os.path.isfile(path):
        raise ApiError('E_RESOURCE_MISSING', "静态资源缺失：%s" % fname)
    with open(path, encoding="utf-8") as f:
        body = f.read()
    return Response(content=body, media_type=ok[fname],
                    headers={"Cache-Control": "no-cache"})


@router.get("/api/health")
async def api_health() -> dict:
    try:
        decide, _, schema, _ = _engine()
        return {"ok": True, "home": GEN_HOME, "page": os.path.isfile(_PAGE),
                "字段数": len(schema.FIELDS), "样例": _samples(),
                "判据目录": os.path.join(GEN_HOME, "判据库"),
                "判据文件": sorted(os.listdir(os.path.join(GEN_HOME, "判据库")))
                if os.path.isdir(os.path.join(GEN_HOME, "判据库")) else [],
                "docx": _docx_version()}
    except Exception as exc:                                      # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc), "home": GEN_HOME}


def _docx_version() -> str:
    try:
        import docx
        return getattr(docx, "__version__", "已安装")
    except Exception:                                             # noqa: BLE001
        return "未安装（无法生成 Word）"


@router.get("/api/template")
async def api_template() -> FileResponse:
    """下载填报模板（含每字段说明与类型）。"""
    _, _, schema, _ = _engine()
    p = os.path.join(OUT_DIR, "_填报模板.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(schema.template(), f, ensure_ascii=False, indent=1)
    return FileResponse(p, media_type="application/json", filename="项目信息表.填报模板.json")


@router.get("/api/samples/{name}")
async def api_sample(name: str) -> dict:
    """取样例内容，方便在页面上直接试。"""
    p = os.path.join(SAMPLE_DIR, os.path.basename(name))
    if not os.path.isfile(p):
        raise ApiError('E_SAMPLE_NOT_FOUND', "没有这个样例")
    with open(p, encoding="utf-8") as f:
        return {"ok": True, "name": os.path.basename(name), "data": json.load(f)}


@router.post("/api/run")
async def api_run(request: Request) -> dict:
    """提交填报表（JSON 文本，或样例名）→ 后台生成。"""
    body = await request.json()
    raw = body.get("data")
    sample = body.get("sample")
    if not raw and sample:
        p = os.path.join(SAMPLE_DIR, os.path.basename(sample))
        if not os.path.isfile(p):
            raise ApiError('E_SAMPLE_NOT_FOUND', "没有这个样例")
        with open(p, encoding="utf-8") as f:
            raw = json.load(f)
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception as exc:                                  # noqa: BLE001
            raise ApiError('E_JSON_INVALID', "填报表不是合法 JSON：%s" % exc)
    if not isinstance(raw, dict):
        raise ApiError('E_NOT_OBJECT', "填报表必须是一个 JSON 对象")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "status": "queued", "log": [],
                         "项目名称": raw.get("项目名称"), "created": time.strftime("%H:%M:%S"),
                         "t0": time.time(), "pct": 4}
    threading.Thread(target=_run_job, args=(job_id, raw, bool(body.get("model"))),
                     daemon=True).start()
    return {"ok": True, "job": job_id}


@router.get("/api/job/{job_id}")
async def api_job(job_id: str) -> dict:
    with _LOCK:
        j = _JOBS.get(job_id)
        if not j:
            raise ApiError('E_JOB_NOT_FOUND', "没有这个任务")
        out = dict(j)
        # 已用秒数由服务端算：客户端的钟可能不准，而且刷新页面后要能接着显示
        t0 = out.get("t0")
        out["secs"] = round(time.time() - t0, 1) if t0 else 0
        out["steps"] = len(STAGES)
        if out.get("status") in ("done", "rejected", "failed"):
            out["pct"] = 100 if out["status"] == "done" else out.get("pct") or 4
    return {"ok": True, "job": out}


@router.get("/api/jobs")
async def api_jobs() -> dict:
    with _LOCK:
        rows = sorted(_JOBS.values(), key=lambda x: x.get("created") or "", reverse=True)[:20]
    return {"ok": True, "jobs": [{"id": r["id"], "status": r["status"],
                                  "项目名称": r.get("项目名称"), "created": r.get("created"),
                                  "file": r.get("file")} for r in rows]}


@router.get("/api/download/{job_id}")
async def api_download(job_id: str) -> FileResponse:
    with _LOCK:
        j = _JOBS.get(job_id)
    if not j or not j.get("file"):
        raise ApiError('E_NO_ARTIFACT', "该任务还没有产物")
    p = os.path.join(OUT_DIR, j["file"])
    if not os.path.isfile(p):
        raise ApiError('E_FILE_NOT_FOUND', "产物已不在磁盘上")
    return FileResponse(p, filename=j["file"],
                        media_type="application/vnd.openxmlformats-officedocument."
                                   "wordprocessingml.document")


@router.get("/api/outputs")
async def api_outputs() -> dict:
    """列出已生成的草稿（便于回看/下载）。"""
    if not os.path.isdir(OUT_DIR):
        return {"ok": True, "files": [], "总数": 0, "dir": OUT_DIR}
    rows = []
    for n in sorted(os.listdir(OUT_DIR), reverse=True):
        if n.endswith(".docx"):
            p = os.path.join(OUT_DIR, n)
            rows.append({"name": n, "size": os.path.getsize(p),
                         "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p)))})
    # `总数` 是给批量删除用的：列表只给最近 50 份，界面上要说清"还有多少份没列出来"，
    # 否则用户批量清完 50 份会以为历史已经空了。
    return {"ok": True, "files": rows[:50], "总数": len(rows), "dir": OUT_DIR}


@router.get("/api/output/{name}")
async def api_output(name: str) -> FileResponse:
    p = os.path.join(OUT_DIR, os.path.basename(name))
    if not os.path.isfile(p):
        raise ApiError('E_FILE_NOT_FOUND', "没有这个文件")
    return FileResponse(p, filename=os.path.basename(name))


def _resolve_output(name: str) -> str:
    """把前端传来的名字收敛成 OUT_DIR 下的一个真实文件。

    `os.path.basename` 挡目录穿越（`../../x.docx` → `x.docx`）；
    再要求后缀是 .docx 且确实存在，避免误删同目录下的模板等文件。
    """
    base = os.path.basename(name or "")
    if not base or not base.endswith(".docx"):
        raise ApiError('E_FILENAME_INVALID', "文件名不合法")
    p = os.path.join(OUT_DIR, base)
    if not os.path.isfile(p):
        raise ApiError('E_FILE_NOT_FOUND', "没有这个文件")
    return p


@router.post("/api/archive")
async def api_archive(request: Request) -> dict:
    """把一份草稿移进 _已归档/ —— **可恢复**，符合项目「归档不删除」纪律。

    只移动、不删除，是历史报告里「归档」按钮的后端。
    """
    body = await request.json()
    src = _resolve_output(body.get("name"))
    os.makedirs(ARCHIVE_DIR, exist_ok=True)
    dst = os.path.join(ARCHIVE_DIR, os.path.basename(src))
    if os.path.exists(dst):        # 同名不覆盖：加时间戳，宁可多留一份也不覆盖旧的
        stem, ext = os.path.splitext(os.path.basename(src))
        dst = os.path.join(ARCHIVE_DIR, "%s-%d%s" % (stem, int(time.time()), ext))
    shutil.move(src, dst)
    return {"ok": True, "归档到": dst, "可恢复": True}


@router.post("/api/delete")
async def api_delete(request: Request) -> dict:
    """**彻底删除**一份草稿 —— 不可恢复，前端二次确认后才调这里。"""
    body = await request.json()
    src = _resolve_output(body.get("name"))
    size = os.path.getsize(src)
    os.remove(src)
    return {"ok": True, "已删除": os.path.basename(src), "释放字节": size, "可恢复": False}


def _trash_dir() -> str:
    """开一个 `_已删除_<时间戳>/`，并只保留最近 TRASH_KEEP 批。"""
    d = os.path.join(OUT_DIR, TRASH_PREFIX + time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(d, exist_ok=True)
    olds = sorted(x for x in os.listdir(OUT_DIR) if x.startswith(TRASH_PREFIX))
    for x in olds[:-TRASH_KEEP]:
        shutil.rmtree(os.path.join(OUT_DIR, x), ignore_errors=True)
    return d


@router.post("/api/delete_batch")
async def api_delete_batch(request: Request) -> dict:
    """批量删除历史草稿（用户要求：「报告编制那个里面可以加一个批量删除历史报告吗」）。

    和单份「删除」的区别，就一处、但很关键：**这一批先移进 `_已删除_<时间戳>/` 再移除**。
    单份删除是点两次确认的"我知道我在删这一份"；批量是"全选 + 手一滑"，
    一次能带走几十份草稿 —— 归档不删除是这个项目的纪律，批量更要留后路。
    （代价只是磁盘上多留一份，界面上会把备份路径告诉用户。）

    先**全部**解析成真实路径再动手：中途抛错时一份都还没移动，
    不会出现"删了一半、界面上一半还在"这种最难解释的状态。
    """
    body = await request.json()
    names = body.get("names")
    # 空名单必须报错，**绝不能**当成"那就全删了吧"
    if not isinstance(names, list) or not names:
        raise ApiError('E_BAD_REQUEST', "没给要删的草稿名")
    paths, missed = [], []
    for n in names:
        try:
            paths.append(_resolve_output(n))
        except ApiError:
            missed.append(os.path.basename(str(n or "")))
    if not paths:
        raise ApiError('E_FILE_NOT_FOUND', "选中的草稿都不在列表里了，刷新一下再看看")
    trash = _trash_dir()
    moved, freed = [], 0
    for p in paths:
        size = os.path.getsize(p)
        base = os.path.basename(p)
        dst = os.path.join(trash, base)
        if os.path.exists(dst):        # 同名不覆盖，宁可多留一份（和归档同一个做法）
            stem, ext = os.path.splitext(base)
            dst = os.path.join(trash, "%s-%d%s" % (stem, int(time.time()), ext))
        shutil.move(p, dst)
        moved.append(base)
        freed += size
    return {"ok": True, "已删除": moved, "没找到": missed, "释放字节": freed,
            "备份目录": trash, "可恢复": True}
