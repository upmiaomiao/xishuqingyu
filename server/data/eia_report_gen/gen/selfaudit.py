# -*- coding: utf-8 -*-
"""生成→自审闭环：把生成的 Word 草稿回灌审核引擎，跑同一套 18 项判据。

为什么这一步是这套工具的关键：**生成的东西能不能过自己家的审核**，当场就知道。
审核引擎本来只吃 PDF，这里做一层"草稿 → 伪解析结果"的适配：

  docx 段落 → 按页（每 N 段一页）切分，模拟 PDF 的 page_text
  docx 表格 → 转成"名称 | 值"文本行（审核的表格识别靠表头关键词，
               这里直接给文本，能命中的就命中，命不中的就是抽取不到 —— 不硬凑）

诚实边界（必须写清楚，否则等于骗人）：
  · 这是**草稿自审**，不是报批件的审核结论。草稿里大量内容标注了【需人工补充】，
    审核引擎抽不到事实时会按"疑似/需人工确认"处理，这是**正确行为**（缺事实不判违规）。
  · 因此自审的价值在于：**发现草稿里已填部分的矛盾与缺失**，而不是给草稿打分。
"""
from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(os.path.dirname(HERE))          # 0911训练/
AUDIT = os.environ.get("AUDIT_HOME") or os.path.join(WORK, "_脚本代码", "审核智能体")
if AUDIT not in sys.path:
    sys.path.insert(0, AUDIT)

PARAS_PER_PAGE = 12          # 草稿没有真实分页，按段落数粗分，仅供审核引擎定位
PLACEHOLDER = "需人工补充"

# 工具自己写的说明段落（定稿前删除），**不进自审**。
# 为什么必须排除：实测自审报过一条**假的存在问题** —— 「生成说明」页里列着
# "未提供的必填项：…是否新增工业废水直排…"，审核的抽取规则读到"废水…直排"就判成本项目直排，
# 于是"符合设置条件、报告却说不用设地表水专项"→ 报存在问题。那是工具在念自己的缺项清单，
# 不是报告在陈述事实。自审的对象是**报告正文**，故这里按标记跳过说明与附录。
META_HEAD = ("生成说明（", "附：")


def _is_meta_head(txt: str) -> bool:
    return any(txt.startswith(h) for h in META_HEAD)


def _has_page_break(p) -> bool:
    return 'w:type="page"' in p._p.xml


def _docx_to_pseudo(path: str):
    """docx → (页文本列表, 表格列表)。见下方 make_draft_report 的说明。"""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    body = doc.element.body
    lines, tables, n_para = [], [], 0
    in_meta = False
    for child in body.iterchildren():
        if child.tag.endswith("}p"):
            p = Paragraph(child, doc)
            txt = p.text.strip()
            if _is_meta_head(txt):
                in_meta = True
            if in_meta:
                if _has_page_break(p):       # 说明页以分页符结束 → 正文从这里继续
                    in_meta = False
                continue
            n_para += 1
            if txt:
                lines.append(txt)
        elif child.tag.endswith("}tbl"):
            if in_meta:                      # 说明页/附录里的表也不审
                continue
            t = Table(child, doc)
            rows = []
            for r in t.rows:
                cells = [c.text.strip() for c in r.cells]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            page = n_para // PARAS_PER_PAGE + 1
            md = "\n".join("| " + " | ".join(r) + " |" for r in rows)
            tables.append({"page": page, "printed_page": None, "mark": None,
                           "rows": rows, "markdown": md})
            lines.extend(" | ".join(r) for r in rows)
    pages, buf = [], []
    for txt in lines:
        buf.append(txt)
        if len(buf) >= PARAS_PER_PAGE:
            pages.append("\n".join(buf))
            buf = []
    if buf:
        pages.append("\n".join(buf))
    return pages, tables


def make_draft_report(path: str):
    """把 Word 草稿包装成审核引擎认的 `ParsedReport`。

    **不自己写一个仿制类** —— 直接构造审核侧的 ParsedReport，这样
    `search / text_range / printed_page / phys_page` 等方法全部原样可用，
    不会出现"桥接层与真实解析层行为不一致"的隐患（那是本项目最忌讳的一类 bug）。

    表格按审核引擎的真实结构给：`{page, printed_page, mark, rows, markdown}`，
    其中 rows 是**逐格二维列表**（不是"每行一个字符串"）；给错结构会直接 KeyError。
    草稿没有版式锚点（anchors 为空），所以审核里的"锚点在不在当页"这类核验会判为不可用 ——
    这是诚实降级，不是错误。
    """
    from audit.parse import ParsedReport

    pages, tables = _docx_to_pseudo(path)
    return ParsedReport(
        pdf=path, sha1="draft-" + os.path.basename(path), pages=len(pages),
        page_text=pages, toc=[], tables=tables, anchors={}, page_labels={},
        page_marks={}, running_lines=[], empty_pages=[], page_offset=0,
        meta={"is_draft": True})


class PseudoReport:
    """已废弃：改为直接构造审核侧的 ParsedReport（见 make_draft_report）。

    保留这个空壳只为让旧引用立刻报错而不是悄悄用错实现 —— 桥接层必须与真实解析层同源。
    """

    def __init__(self, *a, **k):
        raise RuntimeError("请用 make_draft_report()：桥接层不再自造 ParsedReport 仿制类")


def audit_draft(path: str) -> dict:
    """跑审核引擎（判据层 + 规则层），返回分布与"需注意"清单。"""
    from audit.criteria import Criteria
    from audit.runner import judge_report
    from audit.extract import extract_all

    rep = make_draft_report(path)
    C = Criteria()
    ex = extract_all(rep, verbose=False)
    # 不走模型问答：草稿的自述事实已在文本里，抽不到就是"需人工补充"（不猜）
    res = judge_report(rep, ex, C, {}, cond_facts=[], verbose=False)
    items = res.get("items", [])
    dist = {}
    for it in items:
        k = it.get("AI审核")
        dist[k] = dist.get(k, 0) + 1
    need = [it for it in items if it.get("AI审核") in ("存在问题", "存在疑似问题", "优化调整建议")]
    return {
        "适用项数": sum(1 for it in items if it.get("适用") is not False),
        "分布": dist,
        "需注意": [{"审核项": it.get("审核项"), "状态": it.get("AI审核"),
                    "理由": it.get("理由")} for it in need],
        "占位符计数": sum(1 for p in rep.page_text if PLACEHOLDER in p),
        "说明": "草稿自审：草稿中标注【需人工补充】处，审核引擎抽不到事实，会按疑似/需人工确认处理 ——"
                "这是缺事实不判违规的正确行为，不代表草稿有错；本自审用于发现**已填部分**的矛盾与缺失。",
    }


def main():
    if len(sys.argv) < 2:
        print("用法：python selfaudit.py 草稿.docx")
        return 1
    r = audit_draft(sys.argv[1])
    print("适用 %d 项；分布 %s" % (r["适用项数"], r["分布"]))
    for it in r["需注意"]:
        print("- [%s] %s：%s" % (it["状态"], it["审核项"], (it.get("理由") or "")[:90]))
    print(r["说明"])
    return 0


if __name__ == "__main__":
    sys.exit(main())