#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""环评报告审核智能体 · 网页路由（挂进现有 8011 站点，不新起服务）。

为什么不新起一个服务：
  · 8011 已经在跑、已经有 `/doc` 这套"点引用看原文"的能力，加一个页面比重启一个新端口省事；
  · 启动脚本 md5 冻结（不得改动），所以这里只做**包内新增模块 + routes.py 挂载**，
    启动命令、端口、环境变量一律不动。

审核是**长任务**（一份报告解析+模型抽取几十秒到几分钟），所以：
  · POST /audit/api/run 立即返回 job_id，后台线程跑；
  · GET  /audit/api/job/{id} 轮询进度与结果。
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
import uuid

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response

from .errors import ApiError

router = APIRouter(prefix="/audit", tags=["audit"])

AUDIT_HOME = os.environ.get("AUDIT_HOME", "/data/eia_audit")
if AUDIT_HOME not in sys.path:
    sys.path.insert(0, AUDIT_HOME)

# 单份上传报告的大小上限。
# 实测现有 8 份报告是 3.1 ~ 50.0 MB，取 200 MB 留 4 倍余量；
# 再大的基本不是环评报告了，收下来只会白占磁盘和审核时间。
MAX_UPLOAD_BYTES = int(os.environ.get("AUDIT_MAX_UPLOAD_MB", "200")) * 1024 * 1024

_JOBS: dict = {}
_LOCK = threading.Lock()
_PAGE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "frontend", "audit.html")
# 审核结果落盘目录（导出/人工复核都以此为准）
RESULT_DIR = os.path.join(AUDIT_HOME, "_审核结果")


def _engine():
    """延迟导入：审核包的依赖（pymupdf 等）缺失时，不能连累整个 8011 站点点不着。"""
    from audit.runner import audit_file, list_reports, report_dir  # noqa: E402
    return audit_file, list_reports, report_dir


@router.get("/api/reports")
async def api_reports() -> dict:
    try:
        _, list_reports, report_dir = _engine()
    except Exception as exc:
        return {"ok": False, "error": f"审核引擎不可用：{exc}", "dir": AUDIT_HOME, "reports": []}
    try:
        names = list_reports()
    except Exception as exc:
        return {"ok": False, "error": f"列目录失败：{exc}", "dir": AUDIT_HOME, "reports": []}
    root = report_dir()
    return {"ok": True, "dir": root,
            "reports": [{"name": n, "size": os.path.getsize(os.path.join(root, n)),
                         "已审核": _has_result(n)} for n in names]}


def _has_result(name: str) -> bool:
    """这份报告有没有落盘的审核结果（下拉框里标出来，省得用户挨个试）。"""
    try:
        return os.path.isfile(os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json"))
    except OSError:
        return False


@router.get("/api/result/{name}")
async def api_result(name: str) -> dict:
    """取已落盘的审核结果。

    2026-09-22 加：跑完审核会自动切到「原文批注」视图（用户要求"审核完成之后
    默认打开"），但刷新一下 state.result 就没了 —— 用户要么重跑一遍几十分钟的
    审核、要么看不到批注。结果 JSON 本来就躺在磁盘上，读回来就行。
    """
    try:
        name = _safe_name(name)
        path = os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json")
        if not os.path.isfile(path):
            return {"ok": True, "has": False}
        with open(path, encoding="utf-8") as f:
            res = json.load(f)
        return {"ok": True, "has": True, "result": res, **_deliv_info(path)}
    except HTTPException:
        raise
    except Exception as exc:
        raise ApiError('E_INTERNAL', f"读取审核结果失败：{exc}")


# ---------------------------------------------------------------- 清除已完成的审核记录
# 用户要求：「现在报告审核里面都已经审核完成了，删除这些审核完成的，我要重新审核」
# —— 每次演示前都要清一次，所以给界面加个按钮，别每次都找人从运维侧删。
#
# 「审核完成」就是 RESULT_DIR 里有没有 `<报告名>.json`（上面的 _has_result / api_result）。
# 删三样、留两样，少删一样都会留下**对不上号的状态**：
#   删 ① 结果 JSON      —— 不删则下拉框一直标"已审核"，还会把上次结果读回来看；
#   删 ② 人工/<报告名>.json —— 不清会**串**：重审后界面会把上一次的人工修改贴到新结果上；
#   删 ③ 导出/ 交付件    —— 是上一次结果的交付件，结果没了它就是过期文件（仍出现在交付件列表）。
#   留 页图/            —— 页面图缓存，按内容哈希存的，重审能省一次渲染；
#   留 gold评测.json     —— 往次评测记录，**不是**审核结果（引擎自己的 archive_stale.py 也专门跳过它）。
# 删之前**一律整目录备份**：审核一次几十分钟，界面上误点一下全没了的代价太大。
CLEAR_KEEP_BAK = int(os.environ.get("AUDIT_KEEP_BAK", "5"))


def _done_stems() -> list:
    """有审核结果的报告名（不含扩展名）—— 下拉框里的「· 已审核」看的就是这批。"""
    if not os.path.isdir(RESULT_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(RESULT_DIR)
                  if f.endswith(".json") and not f.startswith("gold评测"))


def _backup_results() -> str:
    """整目录备份到 <AUDIT_HOME>/_bak_审核结果_<时间戳>/，只保留最近 CLEAR_KEEP_BAK 份。"""
    parent = os.path.dirname(RESULT_DIR)
    bak = os.path.join(parent, "_bak_审核结果_" + time.strftime("%Y%m%d_%H%M%S"))
    shutil.copytree(RESULT_DIR, bak)
    olds = sorted(d for d in os.listdir(parent) if d.startswith("_bak_审核结果_"))
    for d in olds[:-CLEAR_KEEP_BAK]:                 # 早于最近 N 份的自动清掉，免得越堆越多
        shutil.rmtree(os.path.join(parent, d), ignore_errors=True)
    return bak


@router.post("/api/clear")
async def api_clear() -> dict:
    with _LOCK:
        running = [j for j in _JOBS.values() if not j.get("done")]
    if running:
        raise ApiError('E_AUDIT_RUNNING', "有审核正在跑，等它跑完再清除（否则会删掉正在写的结果）")
    if not os.path.isdir(RESULT_DIR):
        return {"ok": True, "cleared": [], "deleted": [], "backup": ""}
    cleared = _done_stems()
    bak = _backup_results()
    deleted = []
    for f in sorted(os.listdir(RESULT_DIR)):
        p = os.path.join(RESULT_DIR, f)
        if os.path.isfile(p) and f.endswith(".json") and not f.startswith("gold评测"):
            os.remove(p)
            deleted.append(f)
    for sub in ("人工", "导出"):
        d = os.path.join(RESULT_DIR, sub)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            p = os.path.join(d, f)
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
            deleted.append(sub + "/" + f)
    return {"ok": True, "cleared": cleared, "deleted": deleted, "backup": bak}


def _run(job_id: str, name: str, use_llm: bool):
    try:
        audit_file, _, report_dir = _engine()
        root = report_dir()
        path = os.path.join(root, name)
        with _LOCK:
            _JOBS[job_id].update(stage="解析报告", pct=5)
        t0 = time.time()
        res = audit_file(path, use_llm=use_llm, verbose=False)
        # 落盘：导出/人工复核都以这份文件为准。**网页跑完也必须写**，
        # 否则从页面跑出来的报告点"导出"会 404（实测发现）。
        try:
            os.makedirs(RESULT_DIR, exist_ok=True)
            out = os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json")
            with open(out, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=1)
        except Exception as exc:
            res["落盘失败"] = str(exc)
        with _LOCK:
            _JOBS[job_id].update(stage="完成", pct=100, done=True, result=res,
                                 secs=round(time.time() - t0, 1))
    except Exception as exc:
        with _LOCK:
            _JOBS[job_id].update(stage="失败", done=True,
                                 error=f"{exc}", trace=traceback.format_exc()[-1500:])


@router.post("/api/run")
async def api_run(name: str = Query(..., min_length=1, max_length=300),
                  use_llm: bool = Query(default=True)) -> dict:
    try:
        _, list_reports, report_dir = _engine()
        avail = list_reports()
    except Exception as exc:
        raise ApiError('E_ENGINE_UNAVAILABLE', f"审核引擎不可用：{exc}")
    if name not in avail:
        raise ApiError('E_REPORT_NOT_FOUND', "报告不在清单里")
    job_id = uuid.uuid4().hex[:12]
    with _LOCK:
        _JOBS[job_id] = {"id": job_id, "name": name, "stage": "排队", "pct": 1, "done": False}
    threading.Thread(target=_run, args=(job_id, name, use_llm), daemon=True).start()
    return {"ok": True, "job": job_id, "name": name}


def _safe_pdf_name(raw: str) -> str:
    """把上传的文件名收拾成一个能安全落盘的 .pdf 名字。

    只做"变安全"，不做"变好看" —— 环评报告名里有大量中文、括号、顿号、
    全角字符（如「公示版-常德市西部生活垃圾焚烧发电项目（一期工程）环境影响报告书(1).pdf」），
    这些都要原样保留，否则用户认不出哪份是自己的。

    去掉的是：路径分隔符、控制字符、Windows 不允许的 :*?"<>| 。
    """
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    name = re.sub(r"[\x00-\x1f\x7f/\\:*?\"<>|]", "", name).strip(" .")
    if not name:
        name = "上传的报告.pdf"
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    # ext4 单个文件名上限 255 字节，中文一个字 3 字节 → 按字节截
    while len(name.encode("utf-8")) > 200 and len(name) > 8:
        stem, ext = os.path.splitext(name)
        name = stem[:-1] + ext
    return name


def _unique_path(root: str, name: str) -> str:
    """重名时加 (2)(3)…，**绝不覆盖**已有文件。

    不覆盖是硬要求：报告目录里是别人已经审过的原件，
    上传重名文件把它冲掉，等于把历史丢了。
    """
    stem, ext = os.path.splitext(name)
    candidate = os.path.join(root, name)
    i = 2
    while os.path.exists(candidate):
        candidate = os.path.join(root, f"{stem} ({i}){ext}")
        i += 1
    return candidate


def _sha1_of(path: str) -> str:
    import hashlib
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


@router.post("/api/upload")
async def api_upload(file: UploadFile = File(...)) -> dict:
    """上传自己的环评报告，供审核。

    为什么要这个接口（2026-09-18 用户反馈）：
    「环评报告审核这里没有上传自己的环评报告，我觉得这个功能需要有」。
    改动前只能审 `/data/eia_reports` 里已有的 7 份 —— 报告得由人先手工
    拷到服务器上才审得了，网页上没有任何入口。

    流程上有两个必须讲究的地方：

    1. **先写临时文件，校验通过再改名。**
       直接往目标名写的话，传到一半断了就会在报告目录里留下一个半截 PDF；
       `list_reports()` 会把它列出来，点审核时解析报错，而且没人知道那是坏的。
       临时文件用 `.part` 后缀，`list_reports` 只认 `.pdf`，天然不会被列出来。

    2. **内容重复要明确告诉用户，而不是静默去重。**
       `list_reports()` 按文件字节 sha1 去重，只保留排序靠前的那一个名字。
       所以"上传一份和已有报告内容相同的 PDF"会出现：上传成功、但列表里
       看不见新名字 —— 用户会以为上传失败了。这里提前算 sha1 比出来，
       直接告诉他是哪一份，并说明可以直接审那一份。
    """
    try:
        _, list_reports, report_dir = _engine()
        root = report_dir()
    except Exception as exc:
        raise ApiError('E_ENGINE_UNAVAILABLE', f"审核引擎不可用：{exc}")

    raw_name = getattr(file, "filename", "") or ""
    safe = _safe_pdf_name(raw_name)
    if not safe.lower().endswith(".pdf"):
        raise ApiError('E_FILE_TYPE_INVALID', "只支持 PDF 格式的环评报告")

    os.makedirs(root, exist_ok=True)
    tmp_path = os.path.join(root, f".upload-{uuid.uuid4().hex[:10]}.part")
    size = 0
    head = b""
    try:
        import hashlib
        h = hashlib.sha1()
        with open(tmp_path, "wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                if not head:
                    head = chunk[:5]
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise ApiError(
                        'E_FILE_TOO_LARGE',
                        f"文件超过 {MAX_UPLOAD_BYTES // 1048576} MB 上限")
                h.update(chunk)
                out.write(chunk)
        digest = h.hexdigest()

        # 空文件 / 不是 PDF：靠文件头判断，不信扩展名（改个后缀就能骗过扩展名检查）
        if size == 0:
            raise ApiError('E_FILE_TYPE_INVALID', "上传的文件是空的")
        if not head.startswith(b"%PDF"):
            raise ApiError('E_FILE_TYPE_INVALID',
                           "这个文件不是 PDF（文件头不是 %PDF），请确认后重新上传")

        # 内容重复检测：先用文件大小做便宜的预筛，再比 sha1。
        # 报告目录里都是几十 MB 的文件，逐个算 sha1 太慢。
        duplicate_of = ""
        for other in list_reports(only_unique=False):
            op = os.path.join(root, other)
            try:
                if os.path.getsize(op) != size:
                    continue
                if _sha1_of(op) == digest:
                    duplicate_of = other
                    break
            except OSError:
                continue

        if duplicate_of:
            os.remove(tmp_path)
            return {
                "ok": True,
                "duplicate": True,
                "name": duplicate_of,
                "uploaded_as": "",
                "size": size,
                "message": f"这份报告与已有的《{duplicate_of}》内容完全相同，"
                           f"已直接使用已有的那一份，无需重复上传。",
            }

        final_path = _unique_path(root, safe)
        os.replace(tmp_path, final_path)
        name = os.path.basename(final_path)
        renamed = name != safe
        return {
            "ok": True,
            "duplicate": False,
            "name": name,
            "uploaded_as": name,
            "size": size,
            "renamed": renamed,
            "message": (f"已上传《{name}》"
                        + ("（与已有文件重名，已自动改名，原文件未被覆盖）" if renamed else "")),
        }
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError('E_INTERNAL', f"上传失败：{exc}")
    finally:
        # 任何路径下都不留半截临时文件
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass


@router.get("/api/job/{job_id}")
async def api_job(job_id: str) -> dict:
    with _LOCK:
        j = _JOBS.get(job_id)
        if not j:
            raise ApiError('E_JOB_NOT_FOUND', "任务不存在或已过期")
        return dict(j)


@router.get("/api/pdf/{name}")
async def api_pdf(name: str) -> FileResponse:
    """回原文 PDF，供"证据定位"点击后跳到那一页（浏览器 PDF 阅读器 #page=N）。"""
    try:
        _, list_reports, report_dir = _engine()
        if name not in list_reports():
            raise ApiError('E_REPORT_NOT_FOUND', "报告不在清单里")
        path = os.path.join(report_dir(), name)
    except HTTPException:
        raise
    except Exception as exc:
        raise ApiError('E_ENGINE_UNAVAILABLE', str(exc))
    return FileResponse(path, media_type="application/pdf",
                        content_disposition_type="inline", filename=name)


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def audit_page() -> str:
    if not os.path.isfile(_PAGE):
        return HTMLResponse(f"<h3>审核页面缺失：{_PAGE}</h3>", status_code=500)
    with open(_PAGE, encoding="utf-8") as f:
        return HTMLResponse(f.read())


# ---------------------------------------------------------------- 静态资源
# 审核界面是"可挂载模块"（audit_ui.css / audit_ui.js）：独立页 /audit 和
# 问答首页内嵌都用同一份，逻辑只有一处。这里按**白名单**给文件，
# 不做通用目录服务 —— 避免路径穿越（../）。
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
STATIC_OK = {"audit_ui.css": "text/css; charset=utf-8",
             "audit_ui.js": "application/javascript; charset=utf-8",
             # 2026-09-18 重构（阶段 3）：独立页 /audit 的**外壳**资源。
             # 原来这两样内联在 audit.html 里（一段 <style> + 一段 <script>），
             # 而 gen.html 是纯外壳 —— 同一类页面两种做法，所以外置统一。
             # audit_page.css 只放外壳样式（页头、body.embed），不并进 audit_ui.css：
             # 后者是组件的样式表，问答首页内嵌时也会加载，混进去会污染组件。
             "audit_page.css": "text/css; charset=utf-8",
             "audit_page.js": "application/javascript; charset=utf-8",
             # 2026-09-22：原文批注视图独立成模块（audit_ui.js 已经 600 行，
             # 再塞进去会变成第二个"什么都在里面"的文件）。
             "audit_doc.js": "application/javascript; charset=utf-8"}


@router.get("/static/{fname}")
async def audit_static(fname: str):
    if fname not in STATIC_OK:
        raise ApiError('E_RESOURCE_MISSING', "静态资源不存在")
    path = os.path.join(STATIC_DIR, fname)
    if not os.path.isfile(path):
        raise ApiError('E_RESOURCE_MISSING', f"静态资源缺失：{fname}")
    with open(path, encoding="utf-8") as f:
        body = f.read()
    return Response(content=body, media_type=STATIC_OK[fname],
                    headers={"Cache-Control": "no-cache"})


@router.get("/api/health")
async def api_health() -> dict:
    info = {"ok": True, "home": AUDIT_HOME, "page": os.path.isfile(_PAGE)}
    try:
        from audit.criteria import DEFAULT_DIR
        info["判据目录"] = DEFAULT_DIR
        info["判据目录存在"] = os.path.isdir(DEFAULT_DIR)
    except Exception as exc:
        info["ok"] = False
        info["error"] = str(exc)
    try:
        import fitz
        info["pymupdf"] = getattr(fitz, "__doc__", "ok")
    except Exception as exc:
        info["ok"] = False
        info["pymupdf"] = f"缺失：{exc}"
    return info


# ---------------------------------------------------------------- 人工修改 / 导出
# 设计要点：
#   · 人工修改**单独存**，不覆盖 AI 原始结论 —— 否则事后无法审计"AI 原来判了什么"；
#   · 存下来的改动同时就是 **gold 评测集**（人改过 = 人已复核），不用再标一遍；
#   · 导出用 CSV（带 UTF-8 BOM，Excel 直接打开）与 JSON，不引入 xlsx 依赖。
# RESULT_DIR 在文件开头定义（审核落盘也要用）。
REVIEW_DIR = os.path.join(RESULT_DIR, "人工")
# 导出物单独放子目录：否则 `_审核结果/*.json` 里会混进导出文件，
# 被 gold 评测当成"另一份报告"重复计数（实测踩坑）。
EXPORT_DIR = os.path.join(RESULT_DIR, "导出")
STATES = ["存在问题", "存在疑似问题", "优化调整建议", "无问题", "不适用"]


def _safe_name(name: str) -> str:
    if not name or "/" in name or "\\" in name or name.startswith("."):
        raise ApiError('E_FILENAME_INVALID', "文件名非法")
    return name


def _load_ai_result(name: str) -> dict:
    path = os.path.join(RESULT_DIR, name.rsplit(".", 1)[0] + ".json")
    if not os.path.isfile(path):
        raise ApiError('E_REVIEW_NOT_READY', "还没有该报告的审核结果，请先运行审核")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_review(name: str) -> dict:
    """人工复核结果（审核项 → {人工修改, 备注, 时间}）。没有就返回空表。

    2026-09-22 抽成函数：导出 CSV/JSON 与批注版 PDF、意见书都要用它，
    原来这段读取内联在导出路由里，新增两个交付件时必然复制粘贴出三份。
    """
    path = os.path.join(REVIEW_DIR, name.rsplit(".", 1)[0] + ".json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("items") or {}
    except Exception:
        return {}


@router.post("/api/save")
async def api_save(payload: dict) -> dict:
    """保存人工修改（人工修改 + 备注），并返回已保存的项数。"""
    name = _safe_name(str(payload.get("name") or ""))
    items = payload.get("items") or {}
    ai = _load_ai_result(name)
    known = {it["审核项"] for it in ai.get("items", [])}
    bad = [k for k in items if k not in known]
    if bad:
        raise ApiError('E_BAD_REQUEST', f"审核项不存在：{bad[:3]}")
    for k, v in items.items():
        st = (v or {}).get("人工修改") or ""
        if st and st not in STATES:
            raise ApiError('E_BAD_REQUEST', f"结论状态非法：{st}")
    os.makedirs(REVIEW_DIR, exist_ok=True)
    path = os.path.join(REVIEW_DIR, name.rsplit(".", 1)[0] + ".json")
    old = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as f:
            old = json.load(f).get("items") or {}
    old.update({k: {**{kk: vv for kk, vv in (v or {}).items()},
                    "时间": time.strftime("%Y-%m-%d %H:%M:%S")} for k, v in items.items()})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"name": name, "items": old, "版本": "人工复核-1",
                   "更新时间": time.strftime("%Y-%m-%d %H:%M:%S")},
                  f, ensure_ascii=False, indent=1)
    return {"ok": True, "saved": len(items), "file": path}


@router.get("/api/review/{name}")
async def api_review(name: str) -> dict:
    """取回已保存的人工修改（刷新页面后不丢）。"""
    name = _safe_name(name)
    path = os.path.join(REVIEW_DIR, name.rsplit(".", 1)[0] + ".json")
    if not os.path.isfile(path):
        return {"ok": True, "items": {}}
    with open(path, encoding="utf-8") as f:
        return {"ok": True, "items": json.load(f).get("items") or {}}


@router.get("/api/export/{name}")
async def api_export(name: str, fmt: str = Query(default="csv")):
    """导出审核表：csv（Excel 可直接打开）/ json。"""
    name = _safe_name(name)
    ai = _load_ai_result(name)
    review = _load_review(name)
    stem = name.rsplit(".", 1)[0]
    if fmt == "json":
        out = {"file": ai.get("file"), "统计": ai.get("统计"),
               "items": [{**it, "人工修改": (review.get(it["审核项"], {}) or {}).get("人工修改", ""),
                          "复核备注": (review.get(it["审核项"], {}) or {}).get("备注", "")}
                         for it in ai.get("items", [])]}
        os.makedirs(EXPORT_DIR, exist_ok=True)
        path = os.path.join(EXPORT_DIR, stem + ".导出.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        return {"ok": True, "file": os.path.basename(path)}
    cols = ["序号", "审核项", "类别", "AI审核", "人工修改", "最终结论", "置信度",
            "环评文件", "参考依据", "理由", "证据页码", "证据摘录", "需人工确认", "复核备注"]
    import csv
    os.makedirs(EXPORT_DIR, exist_ok=True)
    path = os.path.join(EXPORT_DIR, stem + ".审核表.csv")
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow([f"# 报告：{name}", f"# 页数：{(ai.get('file') or {}).get('pages')}",
                    f"# 统计：{json.dumps(ai.get('统计') or {}, ensure_ascii=False)}"])
        w.writerow(cols)
        for i, it in enumerate(ai.get("items", []), 1):
            rv = review.get(it["审核项"], {}) or {}
            human = rv.get("人工修改") or ""
            ev = it.get("证据") or [{}]
            w.writerow([i, it["审核项"], it.get("类别", ""), it.get("AI审核", ""), human,
                        human or it.get("AI审核", ""), it.get("置信度", ""),
                        it.get("环评文件", ""), it.get("参考依据", ""), it.get("理由", ""),
                        "；".join(f"P{e.get('page')}" for e in ev if e.get("page")),
                        " ‖ ".join(str(e.get("quote", ""))[:120] for e in ev if e.get("quote")),
                        "；".join(it.get("需人工确认") or []), rv.get("备注", "")])
    return {"ok": True, "file": os.path.basename(path)}


@router.get("/api/download/{fname}")
async def api_download(fname: str) -> FileResponse:
    fname = _safe_name(fname)
    path = os.path.join(EXPORT_DIR, fname)
    if not os.path.isfile(path):
        raise ApiError('E_FILE_NOT_FOUND', "文件不存在")
    # 按扩展名给 media type：批注版 PDF / 意见书 docx 都要能直接下载（2026-09-22 新增）
    ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else ""
    media = {"csv": "text/csv", "json": "application/json",
             "pdf": "application/pdf",
             "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             }.get(ext, "application/octet-stream")
    return FileResponse(path, media_type=media, filename=fname)


# ================================================================ 原文批注视图
# 2026-09-22 用户交办：「导出的 json 不好看，能不能做一个类似修订的」。
# 讨论后定的形态：左边报告原文、右边批注，三档定位（精确/近似/仅页码）**档位必须显示**。
# 这一节的三个路由全部是**只读**的：不写报告、不写审核结果、不改判据。
from .audit_anchor import (annot_stats, build_anchors, load_parsed,  # noqa: E402
                           page_payload)

# 解析包（page_text + tables）一份就 1~2 MB，按 sha1 在内存里留最近两份，
# 否则用户每翻一页都要重新读一遍 JSON。
_PARSED: dict = {}
_PARSED_ORDER: list = []
_PARSED_LOCK = threading.Lock()
PARSED_KEEP = 2


def _report_path(name: str) -> str:
    _, list_reports, report_dir = _engine()
    if name not in list_reports():
        raise ApiError('E_REPORT_NOT_FOUND', "报告不在清单里")
    return os.path.join(report_dir(), name)


def _parsed_for(name: str, pdf: str, allow_parse: bool):
    """取解析包（缓存优先）。allow_parse=False 时缺缓存就返回 None（让前端先问一句）。"""
    from audit.parse import sha1_of
    key = sha1_of(pdf)
    with _PARSED_LOCK:
        hit = _PARSED.get(key)
        if hit is not None:
            return hit
    parsed = load_parsed(name, pdf, allow_parse=allow_parse)
    with _PARSED_LOCK:
        if key not in _PARSED:
            _PARSED[key] = parsed
            _PARSED_ORDER.append(key)
            while len(_PARSED_ORDER) > PARSED_KEEP:
                _PARSED.pop(_PARSED_ORDER.pop(0), None)
    return parsed


@router.get("/api/annot/{name}")
async def api_annot(name: str, parse: int = Query(default=1)) -> dict:
    """一次取回：章节树 + 全部批注（含三档定位结果）+ 统计。

    `parse=0` 表示"只用缓存，缺了就告诉我" —— 首次看一份没解析过的报告要几十秒，
    不能让用户对着一个转圈的页面等，得先问一句再解析（前端据此给按钮）。
    """
    name = _safe_name(name)
    ai = _load_ai_result(name)          # 没有审核结果就直接报「请先运行审核」
    pdf = _report_path(name)
    try:
        parsed = await asyncio.to_thread(_parsed_for, name, pdf, bool(parse))
    except FileNotFoundError:
        return {"ok": False, "need_parse": True,
                "message": "这份报告还没有解析缓存，首次查看需要解析一次（几十秒）"}
    except Exception as exc:
        raise ApiError('E_ENGINE_UNAVAILABLE', f"读取报告解析结果失败：{exc}")

    anchors = build_anchors(ai, parsed)
    return {
        "ok": True,
        "name": name,
        "pages": parsed.get("pages"),
        "toc": parsed.get("toc") or [],
        "统计": ai.get("统计") or {},
        "定位统计": annot_stats(anchors),
        "anchors": anchors,
        "empty_pages": parsed.get("empty_pages") or [],
        "page_offset": parsed.get("page_offset"),
        "file": ai.get("file") or {},
    }


@router.get("/api/page/{name}")
async def api_page(name: str, n: int = Query(..., ge=1, le=5000)) -> dict:
    """取第 n 页（物理页）的正文与表格，供批注视图按页懒加载。"""
    name = _safe_name(name)
    pdf = _report_path(name)
    try:
        parsed = await asyncio.to_thread(_parsed_for, name, pdf, False)
    except FileNotFoundError:
        return {"ok": False, "need_parse": True, "message": "还没有解析缓存"}
    return {"ok": True, **page_payload(parsed, n)}


@router.get("/api/pageimg/{name}")
async def api_pageimg(name: str, n: int = Query(..., ge=1, le=5000),
                      z: float = Query(default=1.6, ge=0.5, le=3.0)) -> Response:
    """把某一页渲成 PNG —— 扫描页（没有文本层）在批注视图里要能看见。

    实测 `生物质环评.pdf` 前 5 页文本长度为 0（扫描件），纯文本视图会是一片空白，
    用户会以为报告读不出来。
    """
    name = _safe_name(name)
    pdf = _report_path(name)
    try:
        import pymupdf
    except Exception as exc:
        raise ApiError('E_ENGINE_UNAVAILABLE', f"缺少 pymupdf：{exc}")
    from audit.parse import sha1_of
    cache_dir = os.path.join(RESULT_DIR, "页图", sha1_of(pdf))
    os.makedirs(cache_dir, exist_ok=True)
    out = os.path.join(cache_dir, f"p{n}_z{z}.png")
    if not os.path.isfile(out):
        def _render():
            doc = pymupdf.open(pdf)
            if not (1 <= n <= doc.page_count):
                doc.close()
                raise ApiError('E_BAD_REQUEST', f"页码超出范围（1~{doc.page_count}）")
            pix = doc[n - 1].get_pixmap(matrix=pymupdf.Matrix(z, z))
            data = pix.tobytes("png")
            with open(out, "wb") as f:
                f.write(data)
            doc.close()
        try:
            await asyncio.to_thread(_render)
        except ApiError:
            raise
        except Exception as exc:
            raise ApiError('E_INTERNAL', f"页面渲染失败：{exc}")
    return FileResponse(out, media_type="image/png",
                        headers={"Cache-Control": "no-cache"})


# ================================================================ 交付件导出
# 2026-09-22 用户交办：「导出的 json 之类的不好看」。讨论后定的交付件：
#   · 批注版 PDF —— 原件副本 + 真实 PDF 批注 + 末尾「审核意见汇总」页与落款栏（主交付件）；
#   · 审核意见书 docx —— 打印与签字用（见 audit_docx）。
# 两者都是**只读原件、另存新文件**，绝不覆盖报告本身（归档不删除）。

async def _export_ready(name: str):
    """导出前的公共准备：审核结果 + 解析包（只用缓存） + 批注锚定。"""
    ai = _load_ai_result(name)
    pdf = _report_path(name)
    try:
        parsed = await asyncio.to_thread(_parsed_for, name, pdf, False)
    except FileNotFoundError:
        return None, None, None, {"ok": False, "need_parse": True,
                                  "message": "这份报告还没有解析缓存，请先在「原文批注」视图里解析一次"}
    return ai, pdf, build_anchors(ai, parsed), None


@router.get("/api/export_pdf/{name}")
async def api_export_pdf(name: str) -> dict:
    """生成批注版 PDF。大报告要几十秒（要逐页取字符坐标），前端要提示等待。"""
    name = _safe_name(name)
    ai, pdf, anchors, err = await _export_ready(name)
    if err:
        return err
    try:
        from .audit_pdf import export_pdf
        r = await asyncio.to_thread(export_pdf, name, pdf, ai, None, anchors,
                                    EXPORT_DIR, _load_review(name))
    except Exception as exc:
        raise ApiError('E_INTERNAL', f"生成批注版 PDF 失败：{exc}")
    if r.get("ok"):
        r["download"] = "/audit/api/download/" + urllib.parse.quote(r["file"])
        r.update(_deliv_info(r["path"]))
    return r


@router.get("/api/export_docx/{name}")
async def api_export_docx(name: str) -> dict:
    """生成审核意见书 docx（打印、签字用）。"""
    name = _safe_name(name)
    ai, pdf, anchors, err = await _export_ready(name)
    if err:
        return err
    try:
        from .audit_docx import export_docx
        r = await asyncio.to_thread(export_docx, name, ai, anchors, EXPORT_DIR, _load_review(name))
    except Exception as exc:
        raise ApiError('E_INTERNAL', f"生成审核意见书失败：{exc}")
    if r.get("ok"):
        r["download"] = "/audit/api/download/" + urllib.parse.quote(r["file"])
        r.update(_deliv_info(r["path"]))
    return r


# ================================================================ 交付件：查看与预览
# 2026-09-22 用户问：「这个没办法在网页中预览吗」。
# 结论：**批注版 PDF 可以内联预览**（浏览器自带阅读器，站点的证据跳转一直用的这条路，
# 不需要 PDF.js）；**docx 不能**——浏览器不认这个格式，服务器上也没有 LibreOffice/pandoc/
# 无头浏览器（实测见 `_脚本代码/审核交付/探预览能力.sh`），转不了 PDF。
# 于是意见书额外给一个「网页预览版」：内容与 docx 同源（audit_docx.build_blocks），
# 只是换了个渲染器，浏览器里能直接看、也能直接打印成 PDF。

def _deliv_path(name: str, kind: str) -> str:
    stem = name.rsplit(".", 1)[0]
    return os.path.join(EXPORT_DIR,
                        stem + (".批注版.pdf" if kind == "pdf" else ".审核意见书.docx"))


def _deliv_info(path: str) -> dict:
    try:
        stt = os.stat(path)
    except OSError:
        return {}
    return {"size": stt.st_size,
            "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(stt.st_mtime))}


def _deliv_stale(name: str, path: str) -> bool:
    """交付件是不是"过期"了（审核结果或人工复核比它新）。

    用途：预览时若交付件已是最新，直接打开就行 —— 不必每次都等几十秒重新生成
    （批注版 PDF 大报告要 40s，用户点"预览"等 40s 会以为坏了）。
    """
    try:
        t = os.path.getmtime(path)
    except OSError:
        return True
    stem = name.rsplit(".", 1)[0]
    for src in (os.path.join(RESULT_DIR, stem + ".json"),
                os.path.join(REVIEW_DIR, stem + ".json")):
        try:
            if os.path.getmtime(src) > t:
                return True
        except OSError:
            pass
    return False


@router.get("/api/deliv/{name}")
async def api_deliv(name: str) -> dict:
    """两个交付件生成过没有、多大、什么时候生成的、是不是最新的。

    前端据此决定"预览"是直接打开（秒开）还是先重新生成（几十秒）。
    """
    name = _safe_name(name)
    out = {"ok": True}
    for kind in ("pdf", "docx"):
        p = _deliv_path(name, kind)
        if os.path.isfile(p):
            out[kind] = {"file": os.path.basename(p), "stale": _deliv_stale(name, p),
                         **_deliv_info(p)}
        else:
            out[kind] = None
    return out


@router.get("/api/preview_pdf/{name}")
async def api_preview_pdf(name: str) -> FileResponse:
    """**内联**返回批注版 PDF（浏览器里直接翻，不弹下载框）。

    没生成过就现生成（大报告几十秒）；前端一般会先调 /export_pdf 生成好再打开这里，
    所以正常路径是秒开。
    """
    name = _safe_name(name)
    path = _deliv_path(name, "pdf")
    if not os.path.isfile(path):
        ai, pdf, anchors, err = await _export_ready(name)
        if err:
            raise ApiError('E_BAD_REQUEST', err.get("message") or "还不能生成批注版 PDF")
        try:
            from .audit_pdf import export_pdf
            await asyncio.to_thread(export_pdf, name, pdf, ai, None, anchors,
                                    EXPORT_DIR, _load_review(name))
        except Exception as exc:
            raise ApiError('E_INTERNAL', f"生成批注版 PDF 失败：{exc}")
    if not os.path.isfile(path):
        raise ApiError('E_INTERNAL', "批注版 PDF 没有生成出来")
    return FileResponse(path, media_type="application/pdf",
                        content_disposition_type="inline", filename=os.path.basename(path))


@router.get("/api/preview_docx/{name}", response_class=HTMLResponse)
async def api_preview_docx(name: str) -> str:
    """审核意见书的**网页预览版**（docx 浏览器打不开，这里渲染同一份内容）。"""
    name = _safe_name(name)
    ai, pdf, anchors, err = await _export_ready(name)
    if err:
        raise ApiError('E_BAD_REQUEST', err.get("message") or "还不能生成意见书")
    try:
        from .audit_docx import render_html
        return await asyncio.to_thread(render_html, name, ai, anchors, _load_review(name))
    except Exception as exc:
        raise ApiError('E_INTERNAL', f"生成意见书预览失败：{exc}")
