"""统一错误码与错误响应格式 —— 全站错误响应的唯一归属。

为什么需要这个模块
==================
改动前，本站的错误响应有 **四种互不兼容的形状**（对 65 个用例实测的结果）：

  1. ``{"detail": "报告不在清单里"}``                        42 个 —— HTTPException 的字符串 detail
  2. ``{"detail": [{"loc":…,"msg":…,"type":…}]}``            13 个 —— FastAPI 422，detail 是**数组**
  3. ``Internal Server Error``                               未捕获异常，**纯文本，不是 JSON**
  4. ``{"ok": true, …}``                                     该报错却返回 200 的静默成功

后果全部落在前端：

* 形状 2 让 ``new Error(d.detail)`` 得到 ``[object Object]``（多项时更长，
  实测 5 处：kg.js、gen_ui.js、audit_ui.js ×3）；
* 形状 3 让 ``await r.json()`` 直接抛 SyntaxError，"报错"于是变成"界面什么都不发生"，
  用户读到的是 ``Unexpected token 'I', "Internal S"... is not valid JSON``
  （实测 10 处先 ``r.json()`` 再判 ``r.ok`` 的写法都有这个毛病）；
* 形状 4 让"失败"与"成功但内容为空"在界面上无法区分。

本模块把这四种收敛成一种：

.. code-block:: json

    {
      "ok": false,
      "code": "E_QUERY_EMPTY",
      "message": "问题不能为空",
      "detail": "问题不能为空",
      "tech_detail": "",
      "request_id": "3f9c1a2b"
    }

**兼容性**：``detail`` 字段保留且**保证是字符串** —— 现有前端有 8 处
``new Error(d.detail || '…')`` 直接把它显示给用户，迁移期间不会因为它们而炸。
``code`` 是稳定契约（前端按码分支），``message`` 是给人看的中文（可以改文案，不要改码）。

``request_id`` 出现在响应里，同一串也写进服务端日志，便于"用户截图 → 定位日志"。
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException

# --------------------------------------------------------------------------
# 错误码 → HTTP 状态码
#   码是稳定契约；文案可以改，码不能改（前端按码分支）。
# --------------------------------------------------------------------------
HTTP_STATUS: dict[str, int] = {
    # ---- 4xx：调用方的问题 ----
    "E_BAD_REQUEST":        400,   # 通用，参数不合理但没被 pydantic 拦下
    "E_VALIDATION":         422,   # 请求体/查询串不符合 schema
    "E_QUERY_EMPTY":        400,   # query 与 image 同时为空
    "E_PHOTO_NEEDS_IMAGE":  400,   # report=photo 但没带图
    "E_IMAGE_FORMAT":       400,   # 不是 data:image/ 开头的 data URL
    "E_IMAGE_ENCODING":     400,   # data URL 里没有 ;base64,
    "E_IMAGE_TOO_LARGE":    413,
    "E_FILE_TOO_LARGE":     413,   # 上传的报告文件超过上限
    "E_FILE_TYPE_INVALID":  400,   # 上传的文件类型不对（不是 PDF / 不是真 PDF）
    "E_PATH_UNSAFE":        400,   # 目录穿越、后缀不符
    "E_FILENAME_INVALID":   400,   # 文件名非法
    "E_JSON_INVALID":       400,   # 声称是 JSON 但解析不了
    "E_NOT_OBJECT":         400,   # 要求对象却给了别的类型
    "E_NOT_FOUND":          404,   # 通用
    "E_DOC_NOT_FOUND":      404,   # 原文 .md / PDF
    "E_SESSION_NOT_FOUND":  404,   # 编制会话不存在或已过期
    "E_JOB_NOT_FOUND":      404,   # 任务不存在或已过期
    "E_REPORT_NOT_FOUND":   404,   # 报告不在审核清单里
    "E_SAMPLE_NOT_FOUND":   404,   # 样例不存在
    "E_FILE_NOT_FOUND":     404,   # 产物/静态资源
    "E_NO_ARTIFACT":        404,   # 任务还没有产物
    "E_REVIEW_NOT_READY":   404,   # 还没跑过审核，没有结果可导出
    "E_RESOURCE_MISSING":   404,   # 静态资源不在白名单里
    # ---- 5xx：服务端的问题 ----
    "E_MODEL_UNAVAILABLE":  502,   # 模型服务连不上/报错
    "E_VISION_FAILED":      502,   # 图片识别失败
    "E_RETRIEVE_FAILED":    503,   # 检索服务异常
    "E_ENGINE_UNAVAILABLE": 503,   # 编制/审核引擎不可用
    "E_FRONTEND_MISSING":   500,   # 前端文件缺失（部署事故）
    "E_INTERNAL":           500,   # 未捕获异常
}

# 状态码 → 兜底错误码。给"还没改成 ApiError 的 raise HTTPException"用，
# 保证任何一条路径都不会出现"没有 code"的响应（改动前 55/65 个用例没有码）。
STATUS_FALLBACK: dict[int, str] = {
    400: "E_BAD_REQUEST",
    401: "E_UNAUTHORIZED",
    403: "E_FORBIDDEN",
    404: "E_NOT_FOUND",
    405: "E_METHOD_NOT_ALLOWED",
    409: "E_CONFLICT",
    413: "E_IMAGE_TOO_LARGE",
    422: "E_VALIDATION",
    429: "E_TOO_MANY_REQUESTS",
    500: "E_INTERNAL",
    502: "E_MODEL_UNAVAILABLE",
    503: "E_ENGINE_UNAVAILABLE",
    504: "E_TIMEOUT",
}

# 错误码 → 默认中文文案（构造时不给 message 就用它）
DEFAULT_MESSAGE: dict[str, str] = {
    "E_BAD_REQUEST":        "请求参数不合理",
    "E_VALIDATION":         "请求参数不符合要求",
    "E_QUERY_EMPTY":        "请先输入问题或上传图片",
    "E_PHOTO_NEEDS_IMAGE":  "现场照片专业研判需要上传图片",
    "E_IMAGE_FORMAT":       "图片格式不支持，请上传 PNG / JPG / WebP 图片",
    "E_IMAGE_ENCODING":     "图片编码格式不正确",
    "E_IMAGE_TOO_LARGE":    "图片太大，请压缩后重试",
    "E_PATH_UNSAFE":        "路径不合法",
    "E_FILENAME_INVALID":   "文件名不合法",
    "E_FILE_TOO_LARGE":     "文件太大了，请压缩后再上传",
    "E_FILE_TYPE_INVALID":  "文件格式不支持，请上传 PDF 格式的环评报告",
    "E_JSON_INVALID":       "提交的内容不是合法 JSON",
    "E_NOT_OBJECT":         "提交的内容必须是一个 JSON 对象",
    "E_NOT_FOUND":          "请求的资源不存在",
    "E_DOC_NOT_FOUND":      "没有找到这份原文",
    "E_SESSION_NOT_FOUND":  "会话不存在或已过期，请重新开始",
    "E_JOB_NOT_FOUND":      "任务不存在或已过期",
    "E_REPORT_NOT_FOUND":   "报告不在清单里",
    "E_SAMPLE_NOT_FOUND":   "没有这个样例",
    "E_FILE_NOT_FOUND":     "没有这个文件",
    "E_NO_ARTIFACT":        "该任务还没有产物",
    "E_REVIEW_NOT_READY":   "还没有该报告的审核结果，请先运行审核",
    "E_RESOURCE_MISSING":   "静态资源不存在",
    "E_MODEL_UNAVAILABLE":  "模型服务暂时不可用，请稍后重试",
    "E_VISION_FAILED":      "图片识别失败，请换一张更清晰的图片",
    "E_RETRIEVE_FAILED":    "检索服务暂时不可用，请稍后重试",
    "E_ENGINE_UNAVAILABLE": "引擎暂时不可用，请稍后重试",
    "E_FRONTEND_MISSING":   "前端文件缺失，请联系管理员",
    "E_INTERNAL":           "服务内部错误，请稍后重试或联系管理员",
}

# pydantic 的报错类型 → 中文可读说明。只覆盖实际会遇到的几种，其余回落到原文。
PYDANTIC_MSG: dict[str, str] = {
    "missing":             "缺少必填参数",
    "int_parsing":         "必须是整数",
    "float_parsing":       "必须是数字",
    "bool_parsing":        "必须是布尔值",
    "string_type":         "必须是字符串",
    "list_type":           "必须是数组",
    "dict_type":           "必须是对象",
    "json_invalid":        "请求体不是合法 JSON",
    "less_than_equal":     "取值超出上限",
    "greater_than_equal":  "取值低于下限",
    "string_too_long":     "内容太长",
    "string_too_short":    "内容太短",
    "extra_forbidden":     "包含不认识的字段",
    "value_error":         "取值不合法",
}


class ApiError(HTTPException):
    """带稳定错误码的 HTTP 异常。

    用法::

        raise ApiError("E_QUERY_EMPTY")                    # 用默认文案
        raise ApiError("E_DOC_NOT_FOUND", "没有找到这份原文")
        raise ApiError("E_MODEL_UNAVAILABLE", f"模型服务异常：{exc}", detail=repr(exc))

    ``detail`` 参数（技术细节）不会展示给用户，只写进响应体的 ``tech_detail``，
    便于排查；给用户看的始终是 ``message``。
    """

    def __init__(
        self,
        code: str,
        message: str = "",
        *,
        status: int | None = None,
        detail: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGE.get(code, code)
        self.tech_detail = detail
        st = status if status is not None else HTTP_STATUS.get(code, 400)
        # detail 传字符串 → 保持与改动前一致（现有前端读 d.detail 并展示）
        super().__init__(status_code=st, detail=self.message, headers=headers)


def code_for_status(status: int) -> str:
    """给没带码的 HTTPException 兜一个码，保证响应里永远有 code。"""
    return STATUS_FALLBACK.get(status, "E_BAD_REQUEST" if status < 500 else "E_INTERNAL")


def new_request_id() -> str:
    return uuid.uuid4().hex[:8]


def error_body(
    code: str,
    message: str,
    *,
    detail: str = "",
    request_id: str = "",
) -> dict[str, Any]:
    """统一的错误响应体。

    ``detail`` 与 ``message`` 同值：这是**刻意的兼容**，不是冗余 ——
    现有前端 8 处 ``new Error(d.detail || '…')`` 直接展示该字段，
    改动它是破坏性的。新代码请读 ``code`` + ``message``。
    """
    return {
        "ok": False,
        "code": code,
        "message": message,
        "detail": message,
        "tech_detail": detail,
        "request_id": request_id,
    }


def format_validation_error(errors: list[dict[str, Any]]) -> tuple[str, str]:
    """把 FastAPI 422 的 ``detail`` 数组变成 (给用户看的一句话, 技术细节)。

    改动前这个数组被前端 ``new Error(d.detail)`` 直接 ``String()`` 成
    ``[object Object]``（实测 5 处）。这里把它翻译成人能读的中文。

    示例::

        [{"loc": ["body","top_k"], "msg": "Input should be less than or equal to 10",
          "type": "less_than_equal"}]
        → ("参数 top_k 取值超出上限", 'body.top_k: Input should be less than or equal to 10')
    """
    if not errors:
        return DEFAULT_MESSAGE["E_VALIDATION"], ""

    parts: list[str] = []
    tech: list[str] = []
    for e in errors[:3]:                                   # 最多列三条，避免刷屏
        loc_all = [str(x) for x in (e.get("loc") or [])]
        loc = [x for x in loc_all if x not in ("body", "query", "path")]
        typ = str(e.get("type") or "")
        # JSON 解析错误的 loc 是 ["body", 0]，那个 0 是字符位置不是字段名，
        # 不特判就会拼出"参数「0」请求体不是合法 JSON"这种怪话
        if typ == "json_invalid":
            loc = []
        field = ".".join(loc)
        zh = PYDANTIC_MSG.get(typ)
        if not field:
            # 请求体/查询串整体的问题：不能拼成"参数 请求内容 缺少必填参数"这种别扭的话
            whole = {
                "missing": "请求体不能为空",
                "json_invalid": "请求体不是合法 JSON",
                "dict_type": "请求体必须是一个 JSON 对象",
                "list_type": "请求体必须是一个数组",
            }.get(typ)
            parts.append(whole or (zh or f"请求内容不合法：{e.get('msg', '')}"))
        elif zh:
            parts.append(f"参数「{field}」{zh}")
        else:
            parts.append(f"参数「{field}」不合法：{e.get('msg', '')}")
        tech.append(f"{'.'.join(loc_all)}: {e.get('msg', '')}")

    msg = "；".join(parts)
    if len(errors) > 3:
        msg += f"（共 {len(errors)} 处）"
    return msg, " | ".join(tech)
