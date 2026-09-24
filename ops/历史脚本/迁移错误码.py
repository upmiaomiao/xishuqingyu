#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 raise HTTPException(...) 迁到带错误码的 ApiError(...)。

设计取舍
========
* 用**解析 + 重建**而不是逐条手改：40 多处手改必然漏改或改错一两条，
  而且改完看不出来。脚本化可以做到"映射不到就报错退出"，不静默跳过。
* 保留原来的**消息表达式原文**（f-string / % 格式化 / 变量都原样保留），
  只换外层调用 —— 这样行为差异只有"多了一个 code"，回归风险最小。
* 先 --dry 打印完整对照表供人工过目，再 --apply 落盘。
"""
from __future__ import annotations

import pathlib
import re
import sys

W = pathlib.Path(r"_中间产物/重构工作区/xishu_pipeline")

# 消息文本 → 错误码。键取消息里的**第一个字符串字面量**（去掉 f 前缀）。
BY_MESSAGE: dict[str, str] = {
    # ---- 法规问答 ----
    "query不能为空": "E_QUERY_EMPTY",
    "现场照片专业研判需要上传图片，请用 POST /hybrid_search 并带 image 字段": "E_PHOTO_NEEDS_IMAGE",
    "source 必须是索引里的 .md 路径": "E_PATH_UNSAFE",
    "路径越界": "E_PATH_UNSAFE",
    "未找到原文 PDF：": "E_DOC_NOT_FOUND",
    "静态资源不存在": "E_RESOURCE_MISSING",
    "静态资源缺失：": "E_RESOURCE_MISSING",
    "前端文件缺失：": "E_FRONTEND_MISSING",
    "图片格式不支持，请上传 PNG / JPG / WebP 图片": "E_IMAGE_FORMAT",
    "图片编码格式不正确": "E_IMAGE_ENCODING",
    "图片太大，请压缩后重试（建议长边不超过 1600 像素）": "E_IMAGE_TOO_LARGE",
    "模型服务异常：": "E_MODEL_UNAVAILABLE",
    # ---- 报告编制 ----
    "会话不存在或已过期，请重新开始": "E_SESSION_NOT_FOUND",
    "请把项目情况多写几句（至少一句完整的话）": "E_BAD_REQUEST",
    "还没有收集到任何项目信息": "E_BAD_REQUEST",
    "该任务还没有产物可预览": "E_NO_ARTIFACT",
    "该任务还没有产物": "E_NO_ARTIFACT",
    "产物已不在磁盘上": "E_FILE_NOT_FOUND",
    "没有这个文件": "E_FILE_NOT_FOUND",
    "缺少前端页 frontend/gen.html": "E_FRONTEND_MISSING",
    "没有这个样例": "E_SAMPLE_NOT_FOUND",
    "填报表不是合法 JSON：": "E_JSON_INVALID",
    "填报表必须是一个 JSON 对象": "E_NOT_OBJECT",
    "没有这个任务": "E_JOB_NOT_FOUND",
    "文件名不合法": "E_FILENAME_INVALID",
    # ---- 报告审核 ----
    "审核引擎不可用：": "E_ENGINE_UNAVAILABLE",
    "报告不在清单里": "E_REPORT_NOT_FOUND",
    "任务不存在或已过期": "E_JOB_NOT_FOUND",
    "静态资源缺失：": "E_RESOURCE_MISSING",
    "文件名非法": "E_FILENAME_INVALID",
    "还没有该报告的审核结果，请先运行审核": "E_REVIEW_NOT_READY",
    "审核项不存在：": "E_BAD_REQUEST",
    "结论状态非法：": "E_BAD_REQUEST",
    "文件不存在": "E_FILE_NOT_FOUND",
}

# 消息里没有字符串字面量的（detail=error / str(exc) 之类），按 (文件名, 行号) 指定。
# 行号取"改动前"的行号，脚本会在替换前校验该行确实含有 raise HTTPException。
BY_LINE: dict[tuple[str, int], str] = {
    ("pipeline.py", 445): "E_MODEL_UNAVAILABLE",
    ("audit_routes.py", 126): "E_ENGINE_UNAVAILABLE",
}

RAISE_RE = re.compile(r"^(\s*)raise HTTPException\(")


def find_call(lines: list[str], i: int) -> tuple[int, str]:
    """从第 i 行（0 基）的 raise 开始，返回 (结束行号, 整段文本)。"""
    depth = 0
    buf: list[str] = []
    j = i
    while j < len(lines):
        buf.append(lines[j])
        depth += lines[j].count("(") - lines[j].count(")")
        if depth <= 0:
            break
        j += 1
    return j, "\n".join(buf)


def first_literal(text: str) -> str:
    """取消息表达式里的第一个字符串字面量，用来查 BY_MESSAGE。"""
    for m in re.finditer(r'f?"([^"]*)"', text):
        s = m.group(1)
        if s not in ("status_code", "detail"):
            return s
    return ""


def lookup_code(literal: str) -> str | None:
    """先精确匹配，再按**最长前缀**匹配。

    前缀匹配是为了处理 f-string 里的插值：字面量拿到的是
    ``未找到原文 PDF：{stem}.pdf``，而表里登记的是 ``未找到原文 PDF：``。
    取最长前缀而不是第一个命中，避免 ``静态资源缺失：`` 被 ``静态资源不存在`` 之类的
    短键抢先匹配。
    """
    if literal in BY_MESSAGE:
        return BY_MESSAGE[literal]
    best_key = ""
    best_code: str | None = None
    for k, v in BY_MESSAGE.items():
        if k and literal.startswith(k) and len(k) > len(best_key):
            best_key, best_code = k, v
    return best_code


def extract_detail_expr(text: str) -> str:
    """把 HTTPException(...) 的 detail 参数表达式抠出来。"""
    inner = text[text.index("(") + 1: text.rindex(")")]
    # 去掉 status_code=NNN / NNN, 前缀
    inner = re.sub(r"^\s*status_code\s*=\s*\d+\s*,?", "", inner)
    inner = re.sub(r"^\s*\d+\s*,", "", inner)
    inner = re.sub(r"^\s*detail\s*=\s*", "", inner.strip())
    return inner.strip()


def convert(path: pathlib.Path, dry: bool) -> tuple[int, list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    rows: list[str] = []
    i = 0
    n = 0
    while i < len(lines):
        m = RAISE_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        end, text = find_call(lines, i)
        lineno = i + 1
        detail = extract_detail_expr(text)
        literal = first_literal(detail)
        code = lookup_code(literal) or BY_LINE.get((path.name, lineno))
        if not code:
            raise SystemExit(
                "!! 映射不到错误码：%s L%d\n   literal=%r\n   detail=%r\n"
                "   请先在 BY_MESSAGE 或 BY_LINE 里登记，不要让它静默留在 HTTPException。"
                % (path.name, lineno, literal, detail))
        indent = m.group(1)
        new = f"{indent}raise ApiError({code!r}, {detail})"
        rows.append("  L%-4d %-26s %s" % (lineno, code, literal[:44] or detail[:44]))
        out.append(new)
        n += 1
        i = end + 1
    if not dry and n:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return n, rows


def main() -> int:
    dry = "--apply" not in sys.argv
    files = ["routes.py", "gen_routes.py", "audit_routes.py", "normalize.py",
             "llm.py", "pipeline.py"]
    total = 0
    for name in files:
        p = W / name
        if not p.is_file():
            print("  （跳过 %s，不在工作副本里）" % name)
            continue
        n, rows = convert(p, dry)
        total += n
        print("=" * 96)
        print("%s：%d 处" % (name, n))
        print("=" * 96)
        for r in rows:
            print(r)
    print()
    print("合计 %d 处" % total)
    print("模式：", "DRY RUN（未落盘）" if dry else "已落盘")
    return 0


if __name__ == "__main__":
    sys.exit(main())
